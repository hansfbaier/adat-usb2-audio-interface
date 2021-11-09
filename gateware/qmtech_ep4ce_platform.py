from nmigen import *
from nmigen.build import *

from nmigen_boards.resources import *
from nmigen_boards.qmtech_ep4ce import QMTechEP4CEPlatform

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

        sys_clocks   = Signal(3)
        sound_clocks = Signal(2)

        sys_locked   = Signal()
        sound_locked = Signal()
        reset        = Signal()

        m.submodules.mainpll = Instance("ALTPLL",
            p_BANDWIDTH_TYPE         = "AUTO",
            # 100MHz
            p_CLK0_DIVIDE_BY         = 1,
            p_CLK0_DUTY_CYCLE        = 50,
            p_CLK0_MULTIPLY_BY       = 2,
            p_CLK0_PHASE_SHIFT       = 0,
            # 60MHz
            p_CLK1_DIVIDE_BY         = 5,
            p_CLK1_DUTY_CYCLE        = 50,
            p_CLK1_MULTIPLY_BY       = 6,
            p_CLK1_PHASE_SHIFT       = 0,
            # 30MHz
            p_CLK2_DIVIDE_BY         = 10,
            p_CLK2_DUTY_CYCLE        = 50,
            p_CLK2_MULTIPLY_BY       = 6,
            p_CLK2_PHASE_SHIFT       = 0,

            p_INCLK0_INPUT_FREQUENCY = 20000,
            p_OPERATION_MODE         = "NORMAL",

            # Drive our clock from the USB clock
            # coming from the USB clock pin of the USB3300
            i_inclk  = clk,
            o_clk    = sys_clocks,
            o_locked = sys_locked,
        )

        m.submodules.soundpll = Instance("ALTPLL",
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

            p_INCLK0_INPUT_FREQUENCY = 16667,
            p_OPERATION_MODE         = "NORMAL",

            i_inclk  = sys_clocks[1],
            o_clk    = sound_clocks,
            o_locked = sound_locked,
        )

        m.d.comb += [
            reset.eq(~(sys_locked & sound_locked)),
            ClockSignal("fast").eq(sys_clocks[0]),
            ClockSignal("usb") .eq(sys_clocks[1]),
            ClockSignal("sync").eq(sys_clocks[2]),
            ClockSignal("dac").eq(sound_clocks[1]),
            ClockSignal("adat").eq(sound_clocks[0]),
            ResetSignal("fast").eq(reset),
            ResetSignal("usb") .eq(reset),
            ResetSignal("sync").eq(reset),
            ResetSignal("dac").eq(reset),
            ResetSignal("adat").eq(reset),
        ]

        return m

class ADATFacePlatform(QMTechEP4CEPlatform, LUNAPlatform):
    clock_domain_generator = ADATFaceClockDomainGenerator
    number_of_channels     = 8

    @property
    def file_templates(self):
        templates = super().file_templates
        templates["{{name}}.qsf"] += r"""
            set_global_assignment -name OPTIMIZATION_MODE "Aggressive Performance"
            #set_global_assignment -name FITTER_EFFORT "Standard Fit"
            set_global_assignment -name PHYSICAL_SYNTHESIS_EFFORT "Extra"
            set_instance_assignment -name DECREASE_INPUT_DELAY_TO_INPUT_REGISTER OFF -to *ulpi*
            set_instance_assignment -name INCREASE_DELAY_TO_OUTPUT_PIN OFF -to *ulpi*
            set_global_assignment -name NUM_PARALLEL_PROCESSORS ALL
        """
        templates["{{name}}.sdc"] += r"""
            derive_pll_clocks
            derive_clock_uncertainty
            set_max_delay -from [get_clocks {car|soundpll|auto_generated|pll1|clk[0]}]  -to  [get_clocks {car|mainpll|auto_generated|pll1|clk[2]}] 20
            set_max_delay -from [get_clocks {car|mainpll|auto_generated|pll1|clk[2]}]  -to  [get_clocks {car|soundpll|auto_generated|pll1|clk[0]}] 20
        """
        return templates

    def __init__(self):
        self.resources += ADATFaceRev0Baseboard.resources
        # swap connector numbers, because on ADATface the connector
        # names are swapped compared to the QMTech daughterboard
        self.connectors[0].number = 3
        self.connectors[1].number = 2
        super().__init__(no_kluts=55, standalone=False)