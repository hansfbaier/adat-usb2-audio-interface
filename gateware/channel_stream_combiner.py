from amaranth import *
from amaranth.build import Platform

from amlib.stream        import StreamInterface
from amlib.test          import GatewareTestCase, sync_test_case

class ChannelStreamCombiner(Elaboratable):
    SAMPLE_WIDTH = 24

    def __init__(self, no_lower_channels, no_upper_channels):
        self.no_lower_channels     = no_lower_channels
        self.no_upper_channels     = no_upper_channels
        self.lower_channel_bits    = Shape.cast(range(no_lower_channels)).width
        self.upper_channel_bits    = Shape.cast(range(no_upper_channels)).width
        self.combined_channel_bits = Shape.cast(range(no_lower_channels + no_upper_channels)).width

        self.lower_channel_stream_in = StreamInterface(name="lower_channels",
                                                   payload_width=self.SAMPLE_WIDTH,
                                                   extra_fields=[("channel_nr", self.lower_channel_bits)])

        self.upper_channels_active_in = Signal()
        self.upper_channel_stream_in  = StreamInterface(name="upper_channels",
                                                   payload_width=self.SAMPLE_WIDTH,
                                                   extra_fields=[("channel_nr", self.lower_channel_bits)])

        self.combined_channel_stream_out = StreamInterface(name="combined_channels",
                                                   payload_width=self.SAMPLE_WIDTH,
                                                   extra_fields=[("channel_nr", self.combined_channel_bits)])

        # debug signals
        self.state = Signal(range(3))
        self.upper_channel_counter = Signal(self.upper_channel_bits)

        # debug signals
        self.state = Signal(range(3))

    def elaborate(self, platform: Platform) -> Module:
        m = Module()

        upper_channel_counter = Signal(self.upper_channel_bits)
        m.d.comb += self.upper_channel_counter.eq(upper_channel_counter)

        with m.FSM() as fsm:
            m.d.comb += self.state.eq(fsm.state)

            with m.State("LOWER_CHANNELS"):
                with m.If(  self.combined_channel_stream_out.ready
                          & self.lower_channel_stream_in.valid):
                    m.d.comb += [
                        self.combined_channel_stream_out.payload.eq(self.lower_channel_stream_in.payload),
                        self.combined_channel_stream_out.channel_nr.eq(self.lower_channel_stream_in.channel_nr),
                        self.lower_channel_stream_in.ready.eq(1),
                        self.combined_channel_stream_out.valid.eq(1),
                        self.combined_channel_stream_out.first.eq(self.lower_channel_stream_in.first),
                        self.combined_channel_stream_out.last.eq(0),
                    ]

                    with m.If(self.lower_channel_stream_in.last):
                        m.d.sync += upper_channel_counter.eq(0)
                        with m.If(self.upper_channels_active_in):
                            m.next = "UPPER_CHANNELS"
                        with m.Else():
                            m.next = "FILL_UPPER"

            with m.State("UPPER_CHANNELS"):
                with m.If(self.combined_channel_stream_out.ready):
                    with m.If(self.upper_channels_active_in):
                        with m.If(self.upper_channel_stream_in.valid):
                            m.d.comb += [
                                self.combined_channel_stream_out.payload.eq(self.upper_channel_stream_in.payload),
                                self.combined_channel_stream_out.channel_nr.eq(\
                                    self.no_lower_channels +
                                    self.upper_channel_stream_in.channel_nr),
                                self.upper_channel_stream_in.ready.eq(1),
                                self.combined_channel_stream_out.valid.eq(1),
                                self.combined_channel_stream_out.first.eq(0),
                                self.combined_channel_stream_out.last.eq(self.upper_channel_stream_in.last),
                            ]

                            with m.If(self.upper_channel_stream_in.last):
                                with m.If(self.upper_channel_stream_in.channel_nr == 1):
                                    m.d.sync += upper_channel_counter.eq(2)
                                    m.next = "FILL_UPPER"
                                with m.Else():
                                    m.next = "LOWER_CHANNELS"

                    # USB is not active: Fill in zeros
                    with m.Else():
                        m.next = "FILL_UPPER"

            with m.State("FILL_UPPER"):
                with m.If(self.combined_channel_stream_out.ready):
                    with m.If(  ~self.upper_channels_active_in
                              & self.upper_channel_stream_in.valid):
                        # we just drain all stale data from the upstream FIFOs
                        # if the upper channels are not active
                        m.d.comb += self.upper_channel_stream_in.ready.eq(1)

                    m.d.sync += upper_channel_counter.eq(upper_channel_counter + 1)
                    m.d.comb += [
                        self.combined_channel_stream_out.payload.eq(0),
                        self.combined_channel_stream_out.channel_nr.eq(\
                            self.no_lower_channels +
                            upper_channel_counter),
                        self.combined_channel_stream_out.valid.eq(1),
                        self.combined_channel_stream_out.first.eq(0),
                        self.combined_channel_stream_out.last.eq(0),
                    ]

                    last_channel = upper_channel_counter >= (self.no_upper_channels - 1)
                    with m.If(last_channel):
                        m.d.comb += self.combined_channel_stream_out.last.eq(1)
                        m.next = "LOWER_CHANNELS"

        return m

class ChannelStreamCombinerTest(GatewareTestCase):
    FRAGMENT_UNDER_TEST = ChannelStreamCombiner
    FRAGMENT_ARGUMENTS  = dict(no_lower_channels=32, no_upper_channels=6)

    def send_lower_frame(self, sample: int, channel: int, wait=False):
        yield self.dut.lower_channel_stream_in.channel_nr.eq(channel)
        yield self.dut.lower_channel_stream_in.payload.eq(sample)
        yield self.dut.lower_channel_stream_in.valid.eq(1)
        yield self.dut.lower_channel_stream_in.first.eq(channel == 0)
        yield self.dut.lower_channel_stream_in.last.eq(channel == 31)
        yield
        yield self.dut.lower_channel_stream_in.valid.eq(0)
        if wait:
            yield

    def send_upper_frame(self, sample: int, channel: int, last_channel: int=6, wait=False):
        yield self.dut.upper_channel_stream_in.channel_nr.eq(channel)
        yield self.dut.upper_channel_stream_in.payload.eq(sample)
        yield self.dut.upper_channel_stream_in.valid.eq(1)
        yield self.dut.upper_channel_stream_in.first.eq(channel == 0)
        yield self.dut.upper_channel_stream_in.last.eq(channel == last_channel)
        yield
        yield self.dut.upper_channel_stream_in.valid.eq(0)
        if wait:
            yield

    @sync_test_case
    def test_smoke(self):
        dut = self.dut
        yield
        yield dut.combined_channel_stream_out.ready.eq(1)
        for channel in range(32):
            yield from self.send_lower_frame(channel, channel)
        yield from self.advance_cycles(13)
        for channel in range(32):
            yield from self.send_lower_frame(channel, channel)
        yield from self.advance_cycles(13)
