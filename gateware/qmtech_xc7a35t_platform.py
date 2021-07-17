from nmigen import *
from nmigen.build import *

from luna.gateware.platform.core import LUNAPlatform

from nmigen_boards.resources import *
from nmigen_boards.qmtech_xc7a35t_core import QMTechXC7A35TPlatform


class JT51SynthClockDomainGenerator(Elaboratable):
    def __init__(self, *, clock_frequencies=None, clock_signal_name=None):
        pass

    def elaborate(self, platform):
        m = Module()

        # Create our domains
        m.domains.sync    = ClockDomain()
        m.domains.usb     = ClockDomain()
        m.domains.jt51    = ClockDomain()
        m.domains.jt51int = ClockDomain()
        m.domains.adat    = ClockDomain()

        usb_clock     = Signal()
        sync_clock    = Signal()
        jt51_clock = Signal()
        jt51_clock    = Signal()
        adat_clock    = Signal()

        mainpll_locked   = Signal()
        mainpll_feedback = Signal()

        adatpll_feedback  = Signal()
        adatpll_locked    = Signal()

        jt51pll_feedback = Signal()
        jt51pll_locked   = Signal()

        clk_50 = platform.request(platform.default_clk)

        m.submodules.mainpll = Instance("PLLE2_ADV",
            p_BANDWIDTH            = "OPTIMIZED",
            p_COMPENSATION         = "ZHOLD",
            p_STARTUP_WAIT         = "FALSE",
            p_DIVCLK_DIVIDE        = 1,
            p_CLKFBOUT_MULT        = 30,
            p_CLKFBOUT_PHASE       = 0.000,
            p_CLKOUT0_DIVIDE       = 25,  # 60MHz
            p_CLKOUT0_PHASE        = 0.000,
            p_CLKOUT0_DUTY_CYCLE   = 0.500,
            p_CLKOUT1_DIVIDE       = 50,  # 30MHz
            p_CLKOUT1_PHASE        = 0.000,
            p_CLKOUT1_DUTY_CYCLE   = 0.500,
            p_CLKIN1_PERIOD        = 20,
            i_CLKFBIN              = mainpll_feedback,
            o_CLKFBOUT             = mainpll_feedback,
            i_CLKIN1               = clk_50,
            o_CLKOUT0              = usb_clock,
            o_CLKOUT1              = sync_clock,
            o_LOCKED               = mainpll_locked,
        )

        # 12.288MHz = 48kHz * 256
        m.submodules.adat_pll = Instance("MMCME2_ADV",
            p_BANDWIDTH            = "OPTIMIZED",
            p_COMPENSATION         = "ZHOLD",
            p_STARTUP_WAIT         = "FALSE",
            p_DIVCLK_DIVIDE        = 1,
            p_CLKFBOUT_MULT_F      = 17,
            p_CLKFBOUT_PHASE       = 0.000,
            p_CLKOUT0_DIVIDE_F     = 83,  # 12.288MHz = 48kHz * 256
            p_CLKOUT0_PHASE        = 0.000,
            p_CLKOUT0_DUTY_CYCLE   = 0.500,
            p_CLKIN1_PERIOD        = 16.6666666,
            i_CLKFBIN              = adatpll_feedback,
            o_CLKFBOUT             = adatpll_feedback,
            i_CLKIN1               = usb_clock,
            o_CLKOUT0              = adat_clock,
            o_LOCKED               = adatpll_locked,
        )

        # 56 kHz output sample rate is about 2 cents off of A=440Hz
        # but at least we have a frequency a PLL can generate without
        # a dedicated 3.579545 MHz NTSC crystal
        # 3.584 MHz = 56kHz * 64 (1 sample takes 64 JT51 cycles)
        m.submodules.jt51_pll = Instance("MMCME2_ADV",
            p_BANDWIDTH            = "OPTIMIZED",
            p_COMPENSATION         = "ZHOLD",
            p_STARTUP_WAIT         = "FALSE",
            p_DIVCLK_DIVIDE        = 1,
            p_CLKFBOUT_MULT_F      = 27,
            p_CLKFBOUT_PHASE       = 0.000,
            p_CLKOUT6_DIVIDE       = 113,
            p_CLKOUT6_PHASE        = 0.000,
            p_CLKOUT6_DUTY_CYCLE   = 0.500,
            p_CLKOUT4_CASCADE      = "TRUE",
            p_CLKOUT4_DIVIDE       = 2,
            p_CLKOUT4_PHASE        = 0.000,
            p_CLKOUT4_DUTY_CYCLE   = 0.500,
            p_CLKIN1_PERIOD        = 33.3333333,
            i_CLKFBIN              = jt51pll_feedback,
            o_CLKFBOUT             = jt51pll_feedback,
            i_CLKIN1               = sync_clock,
            o_CLKOUT4              = jt51_clock,
            o_LOCKED               = jt51pll_locked,
        )

        locked = Signal()

        # Connect up our clock domains.
        m.d.comb += [
            locked.eq(mainpll_locked & adatpll_locked & jt51pll_locked),
            ClockSignal("sync").eq(sync_clock),
            ClockSignal("usb").eq(usb_clock),
            ClockSignal("jt51").eq(jt51_clock),
            ClockSignal("adat").eq(adat_clock),
            ResetSignal("sync").eq(locked),
            ResetSignal("jt51").eq(locked),
            ResetSignal("adat").eq(locked),
            ResetSignal("sync").eq(locked),
        ]

        #platform.add_clock_constraint(main_clock, 60e6)

        ground = platform.request("ground")
        m.d.comb += ground.eq(0)

        return m

class JT51SynthPlatform(QMTechXC7A35TPlatform, LUNAPlatform):
    clock_domain_generator = JT51SynthClockDomainGenerator
    default_usb_connection = "ulpi"

    def toolchain_prepare(self, fragment, name, **kwargs):
        plan = super().toolchain_prepare(fragment, name, **kwargs)
        plan.files['top.xdc'] += """
            set ulpi_out [get_ports -regexp ulpi.*(stp|data).*]
            set_output_delay -clock usb_clk 5 $ulpi_out
            set_output_delay -clock usb_clk -1 -min $ulpi_out
            set ulpi_inputs [get_ports -regexp ulpi.*(data|dir|nxt).*]
            set_input_delay -clock usb_clk -min 1 $ulpi_inputs
            set_input_delay -clock usb_clk -max 3.5 $ulpi_inputs
            """

        return plan

    def __init__(self, toolchain="Vivado"):
        self.resources += [
            # USB2 / ULPI section of the USB3300.
            ULPIResource("ulpi", 0,
                data="J_3:31 J_3:29 J_3:27 J_3:25 J_3:23 J_3:21 J_3:19 J_3:17",
                clk="J_3:9", clk_dir="o",
                dir="J_3:11", nxt="J_3:13", stp="J_3:15", rst="J_3:7", rst_invert=True, # USB3320 reset is active low
                attrs=Attrs(IOSTANDARD="LVCMOS18", SLEW="FAST")),

            Resource("ground", 0, Pins(" ".join([f"J_3:{i}" for i in range(8, 33, 2)]), dir="o"), Attrs(IOSTANDARD="LVCMOS18")),

            Resource("debug_led", 0, Pins("J_2:34", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("debug_led", 1, Pins("J_2:36", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("debug_led", 2, Pins("J_2:38", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("debug_led", 3, Pins("J_2:40", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("debug_led", 4, Pins("J_2:42", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("debug_led", 5, Pins("J_2:44", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("debug_led", 6, Pins("J_2:46", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("debug_led", 7, Pins("J_2:48", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),

            UARTResource(0, rx="J_2:8", tx="J_2:10", attrs=Attrs(IOSTANDARD="LVCMOS33")),

            Resource("adat", 0,
                Subsignal("tx", Pins("J_2:12", dir="o")),
                Subsignal("rx", Pins("J_2:14", dir="i")),
                Attrs(IOSTANDARD="LVCMOS33"))
        ]

        super().__init__(standalone=True, toolchain=toolchain)