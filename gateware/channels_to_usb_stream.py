from nmigen                 import *
from nmigen.build           import Platform
from nmigen.lib.fifo        import SyncFIFO
from nmigen_library.stream  import StreamInterface, connect_fifo_to_stream
from nmigen_library.test    import GatewareTestCase, sync_test_case

class ChannelsToUSBStream(Elaboratable):
    def __init__(self, max_nr_channels=2, sample_width=24, max_packet_size=256):
        assert sample_width in [16, 24, 32]

        # parameters
        self._max_nr_channels = max_nr_channels
        self._channel_bits    = Shape.cast(range(max_nr_channels)).width
        self._sample_width    = sample_width
        self._max_packet_size = max_packet_size

        # ports
        self.no_channels_in      = Signal(4)
        self.channel_stream_in   = StreamInterface(name="channel_stream", payload_width=self._sample_width, extra_fields=[("channel_nr", self._channel_bits)])
        self.usb_stream_out      = StreamInterface(name="usb_stream")
        self.data_requested_in   = Signal()
        self.frame_finished_in   = Signal()

        # debug signals
        self.state                   = Signal(2)
        self.level                   = Signal(range(2 * self._max_packet_size + 1))
        self.fifo_level_insufficient = Signal()
        self.done                    = Signal.like(self.level)
        self.out_channel             = Signal(self._channel_bits)
        self.usb_channel             = Signal.like(self.out_channel)
        self.usb_byte_pos            = Signal.like(2)
        self.skipping                = Signal()
        self.filling                 = Signal()

    def elaborate(self, platform: Platform) -> Module:
        m = Module()
        m.submodules.out_fifo = out_fifo = SyncFIFO(width=8 + self._channel_bits, depth=self._max_packet_size + 1, fwft=True)

        channel_stream  = self.channel_stream_in
        channel_payload = Signal(self._sample_width)
        channel_valid   = Signal()
        channel_ready   = Signal()

        out_valid        = Signal()
        out_stream_ready = Signal()

        # latch packet start and end
        first_packet_seen   = Signal()
        frame_finished_seen = Signal()

        with m.If(self.data_requested_in):
            m.d.sync += [
                first_packet_seen.eq(1),
                frame_finished_seen.eq(0),
            ]

        with m.If(self.frame_finished_in):
            m.d.sync += [
                frame_finished_seen.eq(1),
                first_packet_seen.eq(0),
            ]

        m.d.comb += [
            self.usb_stream_out.payload.eq(out_fifo.r_data[:8]),
            self.out_channel.eq(out_fifo.r_data[8:]),
            self.usb_stream_out.valid.eq(out_valid),
            out_stream_ready.eq(self.usb_stream_out.ready),
            channel_payload.eq(channel_stream.payload),
            channel_valid.eq(channel_stream.valid),
            channel_stream.ready.eq(channel_ready),
            self.level.eq(out_fifo.r_level),
        ]

        with m.If(self.usb_stream_out.valid & self.usb_stream_out.ready):
            m.d.sync += self.done.eq(self.done + 1)

        with m.If(self.data_requested_in):
            m.d.sync += self.done.eq(0)

        current_sample       = Signal(32 if self._sample_width > 16 else 16)
        current_channel      = Signal(self._channel_bits)
        current_byte         = Signal(2 if self._sample_width > 16 else 1)

        bytes_per_sample = 4
        last_byte_of_sample = bytes_per_sample - 1

        # USB audio still sends 32 bit samples,
        # even if the descriptor says 24
        shift = 8 if self._sample_width == 24 else 0

        out_fifo_can_write_sample = Signal()
        m.d.comb += out_fifo_can_write_sample.eq(
              out_fifo.w_rdy
            & (out_fifo.w_level < (out_fifo.depth - bytes_per_sample)))

        # this FSM handles writing into the FIFO
        with m.FSM(name="fifo_feeder") as fsm:
            m.d.comb += self.state.eq(fsm.state)

            with m.State("WAIT"):
                m.d.comb += channel_ready.eq(out_fifo_can_write_sample)

                # discard all channels above no_channels_in
                # important for stereo operation
                with m.If(out_fifo_can_write_sample
                          & channel_valid
                          & (channel_stream.channel_nr < self.no_channels_in)):
                    m.d.sync += [
                        current_sample.eq(channel_payload << shift),
                        current_channel.eq(channel_stream.channel_nr),
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

                with m.If(current_byte == last_byte_of_sample):
                    m.d.sync += current_byte.eq(0)
                    m.next = "WAIT"


        channel_counter = Signal(3)
        byte_pos        = Signal(2)
        first_byte      = byte_pos == 0
        last_byte       = byte_pos == 3

        with m.If(out_valid & out_stream_ready):
            m.d.sync += byte_pos.eq(byte_pos + 1)

            with m.If(last_byte):
                m.d.sync += channel_counter.eq(channel_counter + 1)
                with m.If(channel_counter == (self.no_channels_in - 1)):
                    m.d.sync += channel_counter.eq(0)

        with m.If(self.data_requested_in):
            m.d.sync += channel_counter.eq(0)

        fifo_level_sufficient = Signal()
        m.d.comb += [
            self.usb_channel.eq(channel_counter),
            self.usb_byte_pos.eq(byte_pos),
            fifo_level_sufficient.eq(out_fifo.level >= (self.no_channels_in << 2)),
            self.fifo_level_insufficient.eq(~fifo_level_sufficient),
        ]

        with m.If(self.frame_finished_in):
            m.d.sync += byte_pos.eq(0)

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

                # frame ongoing
                with m.If(~frame_finished_seen):
                    # start filling if there are not enough enough samples buffered
                    # for one channel set of audio samples
                    last_channel = self.out_channel == (self._max_nr_channels - 1)

                    with m.If(last_byte & last_channel & ~fifo_level_sufficient):
                        m.next = "FILL"

                    with m.If((self.out_channel != channel_counter)):
                        m.d.comb += [
                            out_fifo.r_en.eq(0),
                            self.usb_stream_out.payload.eq(0),
                            out_valid.eq(1),
                            self.filling.eq(1),
                        ]

                # frame finished: discard extraneous samples
                with m.Else():
                    with m.If(out_fifo.r_rdy & (self.out_channel != 0)):
                        m.d.comb += [
                            out_fifo.r_en.eq(1),
                            out_valid.eq(0),
                        ]
                        m.d.sync += [
                            frame_finished_seen.eq(0),
                            byte_pos.eq(0),
                        ]
                        m.next = "DISCARD"

            with m.State("DISCARD"):
                with m.If(out_fifo.r_rdy):
                    m.d.comb += [
                        out_fifo.r_en.eq(1),
                        out_valid.eq(0),
                        self.skipping.eq(1),
                    ]
                    with m.If(self.out_channel == 0):
                        m.d.comb += out_fifo.r_en.eq(0)
                        m.next = "NORMAL"

            with m.State("FILL"):
                channel_is_ok = fifo_level_sufficient & (self.out_channel == channel_counter)
                with m.If(self.frame_finished_in | channel_is_ok):
                    m.next = "NORMAL"
                with m.Else():
                    m.d.comb += [
                        out_fifo.r_en.eq(0),
                        self.usb_stream_out.payload.eq(0),
                        out_valid.eq(1),
                        self.filling.eq(1),
                    ]

        return m


class ChannelsToUSBStreamTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = ChannelsToUSBStream
    FRAGMENT_ARGUMENTS = dict(max_nr_channels=8)

    def send_one_frame(self, sample: int, channel: int, wait=True):
        yield self.dut.channel_stream_in.channel_nr.eq(channel)
        yield self.dut.channel_stream_in.payload.eq(sample)
        yield self.dut.channel_stream_in.valid.eq(1)
        yield
        if wait:
            yield
            yield
            yield

    @sync_test_case
    def test_smoke(self):
        dut = self.dut
        yield dut.usb_stream_out.ready.eq(0)
        yield dut.frame_finished_in.eq(1)
        yield
        yield dut.frame_finished_in.eq(0)
        yield
        yield
        yield
        yield
        yield
        yield
        yield dut.usb_stream_out.ready.eq(1)
        yield from self.send_one_frame(0x030201, 0, wait=False)
        yield from self.send_one_frame(0x131211, 1)
        yield from self.send_one_frame(0x232221, 2)
        yield from self.send_one_frame(0x333231, 3)
        # source stream stalls, see if we wait
        yield dut.channel_stream_in.valid.eq(0)
        for _ in range(7): yield
        yield from self.send_one_frame(0x434241, 4)
        yield from self.send_one_frame(0x535251, 5)
        yield from self.send_one_frame(0x636261, 6)
        yield from self.send_one_frame(0x737271, 7, wait=False)
        # out stream quits early, see if it
        # consumes extraneous bytes
        yield dut.usb_stream_out.ready.eq(0)
        yield
        for _ in range(15): yield
        yield dut.frame_finished_in.eq(1)
        yield
        yield dut.frame_finished_in.eq(0)
        for _ in range(35): yield
        yield from self.send_one_frame(0x030201, 0)
        yield from self.send_one_frame(0x131211, 1)
        yield dut.usb_stream_out.ready.eq(1)
        yield from self.send_one_frame(0x232221, 2)
        yield from self.send_one_frame(0x333231, 3)
        yield from self.send_one_frame(0x434241, 4)
        yield from self.send_one_frame(0x535251, 5)
        yield from self.send_one_frame(0x636261, 6)
        yield from self.send_one_frame(0x737271, 7)
        yield dut.channel_stream_in.valid.eq(0)
        yield
        for _ in range(45): yield