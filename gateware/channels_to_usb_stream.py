from nmigen                 import *
from nmigen.build           import Platform
from nmigen.lib.fifo        import SyncFIFO
from nmigen_library.stream  import StreamInterface, connect_fifo_to_stream

class ChannelsToUSBStream(Elaboratable):
    def __init__(self, max_nr_channels=2, sample_width=24, max_packet_size=512):
        assert sample_width in [16, 24, 32]

        # parameters
        self._max_nr_channels = max_nr_channels
        self._channel_bits    = Shape.cast(range(max_nr_channels)).width
        self._sample_width    = sample_width
        self._max_packet_size = max_packet_size

        # ports
        self.usb_stream_out      = StreamInterface()
        self.channel_stream_in   = StreamInterface(self._sample_width, extra_fields=[("channel_nr", self._channel_bits)])
        self.packet_start_in     = Signal()

        # debug signals
        self.state               = Signal(2)
        self.level               = Signal(range(self._max_packet_size))
        self.done                = Signal.like(self.level)
        self.out_channel         = Signal(self._channel_bits)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.submodules.out_fifo = out_fifo = SyncFIFO(width=8 + self._channel_bits, depth=self._max_packet_size, fwft=True)

        channel_stream  = self.channel_stream_in
        channel_payload = Signal(self._sample_width)
        channel_valid   = Signal()
        channel_ready   = Signal()

        out_valid = Signal()

        first_packet_seen = Signal()

        with m.If(self.packet_start_in):
            m.d.sync += first_packet_seen.eq(1)

        m.d.comb += [
            self.usb_stream_out.payload.eq(out_fifo.r_data[:8]),
            self.out_channel.eq(out_fifo.r_data[8:]),
            self.usb_stream_out.valid.eq(out_valid),
            channel_payload.eq(channel_stream.payload),
            channel_valid.eq(channel_stream.valid),
            channel_stream.ready.eq(channel_ready),
            self.level.eq(out_fifo.r_level),
        ]

        with m.If(self.usb_stream_out.valid & self.usb_stream_out.ready):
            m.d.sync += self.done.eq(self.done + 1)
        with m.If(self.packet_start_in):
            m.d.sync += self.done.eq(0)

        current_sample       = Signal(32 if self._sample_width > 16 else 16)
        current_channel      = Signal(self._channel_bits)
        current_channel_next = Signal.like(current_channel)
        current_byte         = Signal(2 if self._sample_width > 16 else 1)

        last_channel    = self._max_nr_channels - 1
        num_bytes = 4
        last_byte = num_bytes - 1

        shift = 8 if self._sample_width == 24 else 0

        with m.If(out_fifo.w_rdy):
            # this FSM handles writing into the FIFO
            with m.FSM(name="fifo_feeder") as fsm:
                m.d.comb += [
                    self.state.eq(fsm.state),
                    current_channel_next.eq((current_channel + 1)[:self._channel_bits])
                ]

                with m.State("WAIT-FIRST"):
                    # we have to accept data until we find a first channel sample
                    m.d.comb += channel_ready.eq(1)
                    with m.If(first_packet_seen & channel_valid & (channel_stream.channel_nr == 0)):
                        m.d.sync += [
                            current_sample.eq(channel_payload << shift),
                            current_channel.eq(0),
                        ]
                        m.next = "SEND"

                with m.State("SEND"):
                    m.d.comb += [
                        out_fifo.w_data[:8].eq(current_sample[0:8]),
                        out_fifo.w_data[8:].eq(current_channel),
                        out_fifo.w_en.eq(1),
                    ]
                    m.d.sync += [
                        current_byte.eq(current_byte + 1),
                        current_sample.eq(current_sample >> 8),
                    ]

                    with m.If(current_byte == last_byte):
                        with m.If(channel_valid):
                            m.d.comb += channel_ready.eq(1)

                            m.d.sync += current_channel.eq(current_channel_next)

                            with m.If(current_channel_next == channel_stream.channel_nr):
                                m.d.sync += current_sample.eq(channel_payload << shift)
                                m.next = "SEND"
                            with m.Else():
                                m.next = "FILL-ZEROS"

                        with m.Else():
                            m.next = "WAIT"

                with m.State("WAIT"):
                    with m.If(channel_valid):
                        m.d.comb += channel_ready.eq(1)
                        m.d.sync += [
                            current_sample.eq(channel_payload << shift),
                            current_channel.eq(current_channel_next),
                        ]
                        m.next = "SEND"

                with m.State("FILL-ZEROS"):
                    m.d.comb += [
                        out_fifo.w_data[:8].eq(0),
                        out_fifo.w_data[8:].eq(current_channel),
                        out_fifo.w_en.eq(1),
                    ]
                    m.d.sync += current_byte.eq(current_byte + 1)

                    with m.If(current_byte == last_byte):
                        m.d.sync += current_channel.eq(current_channel_next)
                        with m.If(current_channel == last_channel):
                            m.next = "WAIT-FIRST"

        # this FSM handles reading fron the FIFO
        # this FSM provides robustness against
        # short reads. On next frame all bytes
        # for nonzero channels will be discarded until
        # we reach channel 0 again.
        with m.FSM(name="fifo_postprocess"):
            with m.State("NORMAL"):
                m.d.comb += [
                    out_fifo.r_en.eq(self.usb_stream_out.ready),
                    out_valid.eq(out_fifo.r_rdy)
                ]
                with m.If(self.packet_start_in & (self.out_channel != 0)):
                    m.d.comb += [
                        out_fifo.r_en.eq(1),
                        out_valid.eq(0),
                    ]
                    m.next = "CONSUME"

            with m.State("CONSUME"):
                m.d.comb += [
                    out_fifo.r_en.eq(1),
                    out_valid.eq(0),
                ]
                with m.If(self.out_channel == 0):
                    m.d.comb += out_fifo.r_en.eq(0)
                    m.next = "NORMAL"

        return m