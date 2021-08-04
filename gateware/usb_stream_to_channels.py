from nmigen                 import *
from nmigen.build           import Platform
from nmigen_library.stream  import StreamInterface

class USBStreamToChannels(Elaboratable):
    def __init__(self, nr_channels):
        self._channel_bits = Shape.cast(range(nr_channels)).width

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

        m.d.usb += [
            usb_valid.eq(Cat(self.usb_stream.valid, usb_valid)),
            usb_first.eq(self.usb_stream.first),
            self.channel_stream.valid.eq(0),
        ]

        with m.If(usb_valid):
            m.d.usb += [
                out_byte.eq(self.usb_stream.payload),
                out_byte_counter.eq(out_byte_counter + 1),
            ]

            with m.If(out_byte_counter > 0):
                m.d.usb +=out_sample.eq(Cat(out_sample[8:], out_byte))

            with m.If((out_byte_counter == 0) & ((usb_valid > 1))):
                m.d.usb += [
                    self.channel_stream.payload.eq(out_sample),
                    self.channel_stream.valid.eq(1),
                    out_channel_no.eq(out_channel_no + 1)
                ]

        with m.If(self.usb_stream.first):
            m.d.usb += [
                out_byte_counter.eq(0),
                out_sample.eq(0),
            ]

        with m.If(usb_first):
            m.d.usb += out_channel_no.eq(2**self._channel_bits - 1)

        return m