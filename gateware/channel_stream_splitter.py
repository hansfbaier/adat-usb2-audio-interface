from amaranth import *
from amaranth.build import Platform

from amlib.stream        import StreamInterface
from amlib.test          import GatewareTestCase, sync_test_case

class ChannelStreamSplitter(Elaboratable):
    SAMPLE_WIDTH = 24

    def __init__(self, no_lower_channels, no_upper_channels, test=False):
        self.test = test
        self.no_lower_channels     = no_lower_channels
        self.no_upper_channels     = no_upper_channels
        self.lower_channel_bits    = Shape.cast(range(no_lower_channels)).width
        self.upper_channel_bits    = Shape.cast(range(no_upper_channels)).width
        self.combined_channel_bits = Shape.cast(range(no_lower_channels + no_upper_channels)).width

        self.lower_channel_stream_out = StreamInterface(name="lower_channels",
                                                   payload_width=self.SAMPLE_WIDTH,
                                                   extra_fields=[("channel_nr", self.lower_channel_bits)])

        self.upper_channel_stream_out  = StreamInterface(name="upper_channels",
                                                   payload_width=self.SAMPLE_WIDTH,
                                                   extra_fields=[("channel_nr", self.lower_channel_bits)])

        self.combined_channel_stream_in = StreamInterface(name="combined_channels",
                                                   payload_width=self.SAMPLE_WIDTH,
                                                   extra_fields=[("channel_nr", self.combined_channel_bits)])

        # debug signals

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        if (self.test):
            dummy = Signal()
            m.d.sync += dummy.eq(1)

        input_stream = self.combined_channel_stream_in

        m.d.comb += [
            input_stream.ready.eq(self.lower_channel_stream_out.ready & self.upper_channel_stream_out.ready),
        ]

        with m.If(input_stream.valid & input_stream.ready):
            with m.If(input_stream.channel_nr < self.no_lower_channels):
                m.d.comb += [
                    self.lower_channel_stream_out.payload.eq(input_stream.payload[0:self.no_lower_channels]),
                    self.lower_channel_stream_out.channel_nr.eq(input_stream.channel_nr),
                    self.lower_channel_stream_out.first.eq(input_stream.first),
                    self.lower_channel_stream_out.last.eq(input_stream.channel_nr == (self.no_lower_channels - 1)),
                    self.lower_channel_stream_out.valid.eq(1),
                ]
            with m.Else():
                m.d.comb += [
                    self.upper_channel_stream_out.payload.eq(input_stream.payload[self.no_lower_channels:]),
                    self.upper_channel_stream_out.channel_nr.eq(input_stream.channel_nr - self.no_lower_channels),
                    self.upper_channel_stream_out.first.eq(input_stream.channel_nr == self.no_lower_channels),
                    self.upper_channel_stream_out.last.eq(input_stream.last),
                    self.upper_channel_stream_out.valid.eq(1),
                ]

        return m

class ChannelStreamSplitterTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = ChannelStreamSplitter
    FRAGMENT_ARGUMENTS  = dict(no_lower_channels=32, no_upper_channels=6, test=True)

    def send_frame(self, sample: int, channel: int, wait=False):
        yield self.dut.combined_channel_stream_in.channel_nr.eq(channel)
        yield self.dut.combined_channel_stream_in.payload.eq(sample)
        yield self.dut.combined_channel_stream_in.valid.eq(1)
        yield self.dut.combined_channel_stream_in.first.eq(channel == 0)
        yield self.dut.combined_channel_stream_in.last.eq(channel == 35)
        yield
        yield self.dut.combined_channel_stream_in.valid.eq(0)
        if wait:
            yield

    @sync_test_case
    def test_smoke(self):
        dut = self.dut
        yield
        channels = list(range(36))
        yield from self.advance_cycles(3)

        yield self.dut.lower_channel_stream_out.ready.eq(1)
        yield self.dut.upper_channel_stream_out.ready.eq(1)

        for channel in channels:
            yield from self.send_frame(channel, channel)
        yield from self.advance_cycles(3)


        for channel in channels[:20]:
            yield from self.send_frame(channel, channel)
        yield self.dut.lower_channel_stream_out.ready.eq(0)
        yield from self.send_frame(channels[20], channels[20])
        yield self.dut.lower_channel_stream_out.ready.eq(1)
        for channel in channels[20:32]:
            yield from self.send_frame(channel, channel)
        yield
        for channel in channels[32:34]:
            yield from self.send_frame(channel, channel)
        yield self.dut.upper_channel_stream_out.ready.eq(0)
        yield from self.send_frame(channels[34], channels[34])
        yield self.dut.upper_channel_stream_out.ready.eq(1)
        for channel in channels[34:]:
            yield from self.send_frame(channel, channel)
        yield

