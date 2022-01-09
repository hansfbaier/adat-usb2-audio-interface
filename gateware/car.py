from amaranth import *
from amaranth.build import *

class IntelFPGAClockDomainGenerator(Elaboratable):
    def __init__(self, *, clock_frequencies=None, clock_signal_name=None):
        pass

    def elaborate(self, platform):
        m = Module()

        # Create our domains
        m.domains.usb  = ClockDomain("usb")
        m.domains.sync = ClockDomain("sync")
        m.domains.fast = ClockDomain("fast")
        m.domains.adat = ClockDomain("adat")
        m.domains.dac  = ClockDomain("dac")

        clk = platform.request(platform.default_clk)

        sys_clocks   = Signal(1)
        audio_clocks = Signal(4)
        fast_clock   = Signal()

        sys_locked   = Signal()
        audio_locked = Signal()
        fast_locked  = Signal()
        reset        = Signal()

        m.submodules.mainpll = Instance("ALTPLL",
            p_BANDWIDTH_TYPE         = "AUTO",

            # USB clock: 60MHz
            p_CLK0_DIVIDE_BY         = 5,
            p_CLK0_DUTY_CYCLE        = 50,
            p_CLK0_MULTIPLY_BY       = 6,
            p_CLK0_PHASE_SHIFT       = 0,
            p_CLK2_PHASE_SHIFT       = 0,

            # 50MHz = 20000 picoseconds
            p_INCLK0_INPUT_FREQUENCY = 20000,
            p_OPERATION_MODE         = "NORMAL",

            # Drive our clock from the USB clock
            # coming from the USB clock pin of the USB3300
            i_inclk  = clk,
            o_clk    = sys_clocks,
            o_locked = sys_locked,
        )

        m.submodules.audiopll = Instance("ALTPLL",
            p_BANDWIDTH_TYPE         = "AUTO",

            # ADAT clock = 12.288 MHz = 48 kHz * 256
            p_CLK0_DIVIDE_BY         = 83,
            p_CLK0_DUTY_CYCLE        = 50,
            p_CLK0_MULTIPLY_BY       = 17,
            p_CLK0_PHASE_SHIFT       = 0,

            # I2S DAC clock 48k = 3.072 MHz = 48 kHz * 32 bit * 2 channels
            p_CLK1_DIVIDE_BY         = 83 * 4,
            p_CLK1_DUTY_CYCLE        = 50,
            p_CLK1_MULTIPLY_BY       = 17,
            p_CLK1_PHASE_SHIFT       = 0,

            # ADAT sampling clock = 48 kHz * 256 * 8 times oversampling
            p_CLK2_DIVIDE_BY         = 83,
            p_CLK2_DUTY_CYCLE        = 50,
            p_CLK2_MULTIPLY_BY       = 17 * 8,
            p_CLK2_PHASE_SHIFT       = 0,

            # ADAT transmit domain clock = 48 kHz * 256 * 5 output terminals
            p_CLK3_DIVIDE_BY         = 83,
            p_CLK3_DUTY_CYCLE        = 50,
            p_CLK3_MULTIPLY_BY       = 17 * 5,
            p_CLK3_PHASE_SHIFT       = 0,

            p_INCLK0_INPUT_FREQUENCY = 16667,
            p_OPERATION_MODE         = "NORMAL",

            i_inclk  = sys_clocks[0],
            o_clk    = audio_clocks,
            o_locked = audio_locked,
        )

        m.submodules.fastpll = Instance("ALTPLL",
            p_BANDWIDTH_TYPE         = "AUTO",

            # ADAT sampling clock = 48 kHz * 256 * 8 times oversampling
            p_CLK0_DIVIDE_BY         = 1,
            p_CLK0_DUTY_CYCLE        = 50,
            p_CLK0_MULTIPLY_BY       = platform.fast_multiplier,
            p_CLK0_PHASE_SHIFT       = 0,

            p_INCLK0_INPUT_FREQUENCY = 81395,
            p_OPERATION_MODE         = "NORMAL",

            i_inclk  = audio_clocks[0],
            o_clk    = fast_clock,
            o_locked = fast_locked,
        )


        m.d.comb += [
            reset.eq(~(sys_locked & audio_locked & fast_locked)),
            ClockSignal("fast").eq(fast_clock),
            ClockSignal("usb") .eq(sys_clocks[0]),
            ClockSignal("sync").eq(audio_clocks[3]),
            ClockSignal("dac").eq(audio_clocks[1]),
            ClockSignal("adat").eq(audio_clocks[0]),
            ResetSignal("fast").eq(reset),
            ResetSignal("usb") .eq(reset),
            ResetSignal("sync").eq(reset),
            ResetSignal("dac").eq(reset),
            ResetSignal("adat").eq(reset),
        ]

        return m
