import operator
from functools import reduce

from amaranth                 import *
from amaranth.build           import Platform
from amaranth_library.stream  import StreamInterface
from amaranth_library.test    import GatewareTestCase, sync_test_case

class BundleDemultiplexer(Elaboratable):
    NO_CHANNELS_ADAT = 8
    SAMPLE_WIDTH     = 24

    def __init__(self, no_bundles=4):
        # parameters
        self._no_bundles          = no_bundles
        self._channel_bits        = Shape.cast(range(no_bundles * self.NO_CHANNELS_ADAT)).width
        self._bundle_channel_bits = Shape.cast(range(self.NO_CHANNELS_ADAT)).width

        # ports
        self.channel_stream_in   = StreamInterface(name="channel_stream",
                                                   payload_width=self.SAMPLE_WIDTH,
                                                   extra_fields=[("channel_nr", self._channel_bits)])

        self.bundles_out         = Array(StreamInterface(name=f"output_bundle_{i}",
                                                         payload_width=self.SAMPLE_WIDTH,
                                                         extra_fields=[("channel_nr", self._bundle_channel_bits)])
                                         for i in range(no_bundles))

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        # this is necessary to keep the simulator happy
        keep_sync = Signal()
        m.d.sync += keep_sync.eq(1)

        channel_stream  = self.channel_stream_in
        ready           = Signal()
        bundle_nr       = Signal(range(self._no_bundles))
        channel_nr      = Signal(range(self.NO_CHANNELS_ADAT))

        last_channel = channel_mask = (self.NO_CHANNELS_ADAT - 1)

        m.d.comb += [
            ready.eq(self.bundles_out[bundle_nr].ready),
            channel_stream.ready.eq(ready),
            bundle_nr.eq(channel_stream.channel_nr >> channel_nr.width),
            channel_nr.eq(channel_stream.channel_nr & channel_mask)
        ]

        with m.If(ready & channel_stream.valid):
            m.d.comb += [
                self.bundles_out[bundle_nr].valid.eq(1),
                self.bundles_out[bundle_nr].payload.eq(channel_stream.payload),
                self.bundles_out[bundle_nr].channel_nr.eq(channel_nr),
                self.bundles_out[bundle_nr].first.eq(channel_nr == 0),
                self.bundles_out[bundle_nr].last.eq(channel_nr == last_channel),
            ]

        return m

class BundleDemultiplexerTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = BundleDemultiplexer
    FRAGMENT_ARGUMENTS  = dict()

    def send_one_frame(self, sample: int, channel: int, wait=True):
        yield self.dut.channel_stream_in.channel_nr.eq(channel)
        yield self.dut.channel_stream_in.payload.eq(sample)
        yield self.dut.channel_stream_in.valid.eq(1)
        yield
        yield self.dut.channel_stream_in.valid.eq(0)
        if wait:
            yield

    @sync_test_case
    def test_smoke(self):
        dut = self.dut
        for bundle in range(4):
            yield dut.bundles_out[bundle].ready.eq(1)
        yield
        yield
        for sample in range(3):
            for ch in range(4*BundleDemultiplexer.NO_CHANNELS_ADAT):
                yield from self.send_one_frame((sample << 8) | ch, ch, wait=False)

        yield
        yield
