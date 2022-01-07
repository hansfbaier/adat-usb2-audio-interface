from amaranth import *
from amaranth.build import *

from amaranth_boards.resources import *
from amaranth_boards.qmtech_ep4ce import QMTechEP4CEPlatform

from luna.gateware.platform.core import LUNAPlatform
from luna.gateware.platform      import NullPin

from adatface_rev0_baseboard import ADATFaceRev0Baseboard

class ADATFaceClockDomainGenerator(Elaboratable):
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

class ADATFacePlatform(QMTechEP4CEPlatform, LUNAPlatform):
    fast_multiplier        = 9
    clock_domain_generator = ADATFaceClockDomainGenerator
    fast_domain_clock_freq = int(48e3 * 256 * fast_multiplier)

    @property
    def file_templates(self):
        templates = super().file_templates
        templates["{{name}}.qsf"] += r"""
            set_global_assignment -name OPTIMIZATION_MODE "Aggressive Performance"
            set_global_assignment -name FITTER_EFFORT "Standard Fit"
            set_global_assignment -name PHYSICAL_SYNTHESIS_EFFORT "Extra"
            set_instance_assignment -name DECREASE_INPUT_DELAY_TO_INPUT_REGISTER OFF -to *ulpi*
            set_instance_assignment -name INCREASE_DELAY_TO_OUTPUT_PIN OFF -to *ulpi*
            set_global_assignment -name NUM_PARALLEL_PROCESSORS ALL
        """
        templates["{{name}}.sdc"] += r"""
            derive_pll_clocks
            derive_clock_uncertainty
            # sync clock domain crossing to ADAT clock domain crossing
            set_max_delay -from [get_clocks {car|audiopll|auto_generated|pll1|clk[3]}]  -to  [get_clocks {car|audiopll|auto_generated|pll1|clk[0]}] 5

            # USB to fast clock domain crossing
            set_max_delay -from [get_clocks {car|mainpll|auto_generated|pll1|clk[0]}]  -to  [get_clocks {car|fastopll|auto_generated|pll1|clk[0]}] 5
        """
        return templates

    def __init__(self):
        self.resources += ADATFaceRev0Baseboard.resources
        # swap connector numbers, because on ADATface the connector
        # names are swapped compared to the QMTech daughterboard
        self.connectors[0].number = 3
        self.connectors[1].number = 2
        super().__init__(no_kluts=55, standalone=False)