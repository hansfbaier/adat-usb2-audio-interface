from amaranth          import *
from amaranth.lib.fifo import SyncFIFO
from amaranth.build    import Platform

from amlib.stream import StreamInterface, connect_fifo_to_stream

class StereoPairExtractor(Elaboratable):
    def __init__(self, max_no_channels: int):
        self._channel_bits    = Shape.cast(range(max_no_channels)).width

        # I/O
        self.channel_stream_in   = StreamInterface(name="channel_stream_in", payload_width=24, extra_fields=[("channel_nr", self._channel_bits)])
        self.selected_channel_in = Signal(range(max_no_channels))
        # the first=left and last=right signals mark the channel on the output stream
        self.channel_stream_out  = StreamInterface(name="channel_stream_out", payload_width=24)

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        m.submodules.fifo = fifo = SyncFIFO(width=24+1, depth=16*2)

        in_channel_nr  = self.channel_stream_in.channel_nr
        out_channel_nr = Signal(self._channel_bits)

        # the ready signal is not wired in the input stream because this
        # module must not exert upstream back pressure
        with m.If(  self.channel_stream_in.valid
                  & (  (in_channel_nr == self.selected_channel_in)
                     | (in_channel_nr == (self.selected_channel_in + 1)))):

            m.d.comb += [
                fifo.w_data.eq(Cat(self.channel_stream_in.payload, out_channel_nr[0])),
                fifo.w_en.eq(1)
            ]

        m.d.comb += [
            out_channel_nr.eq(in_channel_nr - self.selected_channel_in),
            *connect_fifo_to_stream(fifo, self.channel_stream_out),
            self.channel_stream_out.first.eq(~fifo.r_data[-1]),
            self.channel_stream_out.last.eq(fifo.r_data[-1]),
        ]

        return m