from nmigen                 import *
from nmigen.build           import Platform
from nmigen_library.stream  import StreamInterface

class USBStreamToChannels(Elaboratable):
    def __init__(self, max_no_channels=2):
        # parameters
        self._max_nr_channels = max_no_channels
        self._channel_bits    = Shape.cast(range(max_no_channels)).width

        # ports
        self.no_channels_in      = Signal(self._channel_bits + 1)
        self.usb_stream_in       = StreamInterface()
        self.channel_stream_out  = StreamInterface(24, extra_fields=[("channel_nr", self._channel_bits)])

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        out_channel_nr   = Signal(self._channel_bits)
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
            with m.FSM() as fsm:
                with m.State("B0"):
                    with m.If(usb_first):
                        m.d.sync += out_channel_nr.eq(0)
                    with m.Else():
                        m.d.sync += out_channel_nr.eq(out_channel_nr + 1)
                    m.next = "B1"

                with m.State("B1"):
                    with m.If(usb_first):
                        m.d.sync += out_channel_nr.eq(0)
                        m.next = "B1"
                    with m.Else():
                        m.d.sync += out_sample[:8].eq(usb_payload)
                        m.next = "B2"

                with m.State("B2"):
                    with m.If(usb_first):
                        m.d.sync += out_channel_nr.eq(0)
                        m.next = "B1"
                    with m.Else():
                        m.d.sync += out_sample[8:16].eq(usb_payload)
                        m.next = "B3"

                with m.State("B3"):
                    with m.If(usb_first):
                        m.d.sync += out_channel_nr.eq(0)
                        m.next = "B1"
                    with m.Else():
                        m.d.sync += [
                            self.channel_stream_out.payload.eq(Cat(out_sample, usb_payload)),
                            self.channel_stream_out.valid.eq(1),
                            self.channel_stream_out.channel_nr.eq(out_channel_nr),
                            self.channel_stream_out.first.eq(out_channel_nr == 0),
                            self.channel_stream_out.last.eq(out_channel_nr == last_channel),
                        ]

                        with m.If(out_channel_nr == last_channel):
                            m.d.sync += out_channel_nr.eq(-1)

                        m.next = "B0"

        return m