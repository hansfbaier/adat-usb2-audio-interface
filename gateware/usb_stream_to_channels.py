from nmigen                 import *
from nmigen.build           import Platform
from nmigen_library.stream  import StreamInterface

class USBStreamToChannels(Elaboratable):
    def __init__(self, nr_channels):
        self._nr_channels   = nr_channels
        self._channel_bits  = Shape.cast(range(nr_channels)).width
        self.usb_stream     = StreamInterface()
        self.channel_stream = StreamInterface(24, extra_fields=[("channel_no", self._channel_bits)])

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        out_channel_no   = Signal(self._channel_bits)
        out_byte         = Signal(8)
        out_byte_counter = Signal(2)
        out_sample       = Signal(24)
        usb_valid        = Signal(2)
        usb_first        = Signal()

        out_valid = self.channel_stream.valid

        m.d.sync += [
            usb_valid.eq(Cat(self.usb_stream.valid, usb_valid)),
            usb_first.eq(self.usb_stream.first),
            out_valid.eq(0),
        ]

        with m.If((0 < usb_valid) & self.channel_stream.ready):
            m.d.sync += [
                out_byte.eq(self.usb_stream.payload),
                out_byte_counter.eq(out_byte_counter + 1),
            ]

            with m.If(out_byte_counter > 0):
                m.d.sync +=out_sample.eq(Cat(out_sample[8:], out_byte))

            with m.If((out_byte_counter == 0) & ((usb_valid > 1))):
                m.d.sync += [
                    self.channel_stream.payload.eq(out_sample),
                    out_valid.eq(1),
                    out_channel_no.eq(out_channel_no + 1)
                ]

        with m.If(self.usb_stream.first & self.usb_stream.valid):
            m.d.sync += out_byte_counter.eq(0)

        with m.If(usb_first & usb_valid):
            m.d.sync += out_channel_no.eq(2**self._channel_bits - 1)

        m.d.comb += [
            self.usb_stream.ready.eq(self.channel_stream.ready),
            self.channel_stream.first.eq(
                (out_channel_no == 0) & out_valid),
            self.channel_stream.last.eq(
                (out_channel_no == (self._nr_channels - 1)) & out_valid),
            self.channel_stream.channel_no.eq(out_channel_no),
        ]

        return m