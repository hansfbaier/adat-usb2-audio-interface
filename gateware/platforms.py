from amaranth import *
from amaranth.build import *

from amaranth_boards.resources import *
from amaranth_boards.qmtech_ep4ce   import QMTechEP4CEPlatform
from amaranth_boards.qmtech_5cefa2  import QMTech5CEFA2Platform
from amaranth_boards.qmtech_10cl006 import QMTech10CL006Platform

from luna.gateware.platform.core import LUNAPlatform

from car                     import IntelFPGAClockDomainGenerator
from adatface_rev0_baseboard import ADATFaceRev0Baseboard

class IntelFPGAParameters:
    QSF_ADDITIONS = r"""
            set_global_assignment -name OPTIMIZATION_MODE "Aggressive Performance"
            set_global_assignment -name FITTER_EFFORT "Standard Fit"
            set_global_assignment -name PHYSICAL_SYNTHESIS_EFFORT "Extra"
            set_instance_assignment -name DECREASE_INPUT_DELAY_TO_INPUT_REGISTER OFF -to *ulpi*
            set_instance_assignment -name INCREASE_DELAY_TO_OUTPUT_PIN OFF -to *ulpi*
            set_global_assignment -name NUM_PARALLEL_PROCESSORS ALL
        """

    SDC_ADDITIONS = r"""
            derive_pll_clocks
            derive_clock_uncertainty
            # sync clock domain crossing to ADAT clock domain crossing
            set_max_delay -from [get_clocks {car|audiopll|auto_generated|pll1|clk[3]}]  -to  [get_clocks {car|audiopll|auto_generated|pll1|clk[0]}] 5

            # USB to fast clock domain crossing
            set_max_delay -from [get_clocks {car|mainpll|auto_generated|pll1|clk[0]}]  -to  [get_clocks {car|fastopll|auto_generated|pll1|clk[0]}] 5
        """

class ADATFaceCycloneV(QMTech5CEFA2Platform, LUNAPlatform):
    fast_multiplier        = 9
    clock_domain_generator = IntelFPGAClockDomainGenerator
    fast_domain_clock_freq = int(48e3 * 256 * fast_multiplier)

    @property
    def file_templates(self):
        templates = super().file_templates
        templates["{{name}}.qsf"] += IntelFPGAParameters.QSF_ADDITIONS
        templates["{{name}}.sdc"] += IntelFPGAParameters.SDC_ADDITIONS
        return templates

    def __init__(self):
        self.resources += ADATFaceRev0Baseboard.resources
        # swap connector numbers, because on ADATface the connector
        # names are swapped compared to the QMTech daughterboard
        self.connectors[0].number = 3
        self.connectors[1].number = 2
        super().__init__(standalone=False)

class ADATFaceCycloneIV(QMTechEP4CEPlatform, LUNAPlatform):
    fast_multiplier        = 9
    clock_domain_generator = IntelFPGAClockDomainGenerator
    fast_domain_clock_freq = int(48e3 * 256 * fast_multiplier)

    @property
    def file_templates(self):
        templates = super().file_templates
        templates["{{name}}.qsf"] += IntelFPGAParameters.QSF_ADDITIONS
        templates["{{name}}.sdc"] += IntelFPGAParameters.SDC_ADDITIONS
        return templates

    def __init__(self):
        self.resources += ADATFaceRev0Baseboard.resources
        # swap connector numbers, because on ADATface the connector
        # names are swapped compared to the QMTech daughterboard
        self.connectors[0].number = 3
        self.connectors[1].number = 2
        super().__init__(no_kluts=55, standalone=False)

# This is here just for experimental reasons.
# right now the design probably would not fit into this device anymore
class ADATFaceCyclone10(QMTech10CL006Platform, LUNAPlatform):
    clock_domain_generator = IntelFPGAClockDomainGenerator
    default_usb_connection = "ulpi"
    number_of_channels     = 8
    bitwidth               = 24

    @property
    def file_templates(self):
        templates = super().file_templates
        templates["{{name}}.qsf"] += IntelFPGAParameters.QSF_ADDITIONS
        templates["{{name}}.sdc"] += IntelFPGAParameters.SDC_ADDITIONS
        return templates

    def __init__(self):
        self.resources += ADATFaceRev0Baseboard.resources
        # swap connector numbers, because on ADATface the connector
        # names are swapped compared to the QMTech daughterboard
        self.connectors[0].number = 3
        self.connectors[1].number = 2

        super().__init__(standalone=False)