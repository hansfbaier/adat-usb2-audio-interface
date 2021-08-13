from nmigen                 import *
from nmigen.build           import Platform
from nmigen_library.stream  import StreamInterface

class USBStreamToChannels(Elaboratable):
    def __init__(self, max_nr_channels):
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
        out_byte         = Signal(8)
        out_byte_counter = Signal(2)
        out_sample       = Signal(24)
        usb_valid        = Signal(2)
        usb_first        = Signal()

        out_valid = self.channel_stream_out.valid

        m.d.sync += [
            usb_valid.eq(Cat(self.usb_stream_in.valid, usb_valid)),
            usb_first.eq(self.usb_stream_in.first),
            out_valid.eq(0),
        ]

        with m.If((0 < usb_valid) & self.channel_stream_out.ready):
            m.d.sync += [
                out_byte.eq(self.usb_stream_in.payload),
                out_byte_counter.eq(out_byte_counter + 1),
            ]

            with m.If(out_byte_counter > 0):
                m.d.sync +=out_sample.eq(Cat(out_sample[8:], out_byte))

            with m.If((out_byte_counter == 0) & ((usb_valid > 1))):
                m.d.sync += [
                    self.channel_stream_out.payload.eq(out_sample),
                    out_valid.eq(1),
                    out_channel_no.eq(out_channel_no + 1)
                ]

        with m.If(self.usb_stream_in.first & self.usb_stream_in.valid):
            m.d.sync += out_byte_counter.eq(0)

        with m.If(usb_first & usb_valid):
            m.d.sync += out_channel_no.eq(2**self._channel_bits - 1)

        m.d.comb += [
            self.usb_stream_in.ready.eq(self.channel_stream_out.ready),
            self.channel_stream_out.first.eq(
                (out_channel_no == 0) & out_valid),
            self.channel_stream_out.last.eq(
                (out_channel_no == (self.no_channels_in - 1)) & out_valid),
            self.channel_stream_out.channel_no.eq(out_channel_no),
        ]

        return m