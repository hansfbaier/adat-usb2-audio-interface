from nmigen                 import *
from nmigen.build           import Platform
from nmigen_library.stream  import StreamInterface

class USBStreamToChannels(Elaboratable):
    def __init__(self, max_nr_channels=2):
        # parameters
        self._max_nr_channels = max_nr_channels
        self._channel_bits    = Shape.cast(range(max_nr_channels)).width

        # ports
        self.no_channels_in      = Signal(self._channel_bits + 1)
        self.usb_stream_in       = StreamInterface()
        self.channel_stream_out  = StreamInterface(24, extra_fields=[("channel_no", self._channel_bits)])

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        out_channel_no   = Signal(self._channel_bits)
        out_sample       = Signal(16)
        usb_valid        = Signal()
        usb_first        = Signal()
        usb_payload      = Signal(8)
        out_ready        = Signal()

        last_channel  = Signal(self._channel_bits)

        m.d.comb += [
            usb_first.eq(self.usb_stream_in.first),
            usb_valid.eq(self.usb_stream_in.valid),
            usb_payload.eq(self.usb_stream_in.payload),
            out_ready.eq(self.channel_stream_out.ready),
            self.usb_stream_in.ready.eq(out_ready),
            last_channel.eq(self.no_channels_in - 1),
        ]

        m.d.sync += [
            self.channel_stream_out.valid.eq(0),
            self.channel_stream_out.first.eq(0),
            self.channel_stream_out.last.eq(0),
        ]

        with m.If(usb_valid & out_ready):
            with m.FSM():
                with m.State("B0"):
                    with m.If(usb_first):
                        m.d.sync += out_channel_no.eq(0)
                    with m.Else():
                        m.d.sync += out_channel_no.eq(out_channel_no + 1)

                    m.next = "B1"

                with m.State("B1"):
                    m.d.sync += out_sample[:8].eq(usb_payload)
                    m.next = "B2"

                with m.State("B2"):
                    m.d.sync += out_sample[8:16].eq(usb_payload)
                    m.next = "B3"

                with m.State("B3"):
                    m.d.sync += [
                        self.channel_stream_out.payload.eq(Cat(out_sample, usb_payload)),
                        self.channel_stream_out.valid.eq(1),
                        self.channel_stream_out.channel_no.eq(out_channel_no),
                        self.channel_stream_out.first.eq(out_channel_no == 0),
                        self.channel_stream_out.last.eq(out_channel_no == last_channel),
                    ]

                    with m.If(out_channel_no == last_channel):
                        m.d.sync += out_channel_no.eq(-1)

                    m.next = "B0"

        return m