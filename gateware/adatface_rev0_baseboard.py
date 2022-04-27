from amaranth.build import *
from amaranth_boards.resources import *

class ADATFaceRev0Baseboard:
    @staticmethod
    def resources(attrs, colorlight=False):
        return [
            # LEDS
            Resource("leds", 0,
                Subsignal("host",       Pins ("J_3:60", dir="o")),
                Subsignal("usb1",       Pins ("J_3:57", dir="o")),
                Subsignal("usb2",       Pins ("J_3:58", dir="o")),
                Subsignal("sync1",      Pins ("J_3:55", dir="o")),
                Subsignal("sync2",      Pins ("J_3:56", dir="o")),
                Subsignal("sync3",      Pins ("J_3:53", dir="o")),
                Subsignal("sync4",      Pins ("J_3:54", dir="o")),
                Subsignal("active1",    Pins ("J_3:51", dir="o")),
                Subsignal("active2",    Pins ("J_3:49", dir="o")),
                Subsignal("suspended1", Pins ("J_3:52", dir="o")),
                Subsignal("suspended2", Pins ("J_3:50", dir="o")),
                attrs),


            # USB
            ULPIResource("ulpi", 1,
                data="J_3:37 J_3:38 J_3:39 J_3:40 J_3:41 J_3:42 J_3:43 J_3:44",
                clk="J_3:27", clk_dir="o", # this needs to be a clock pin of the FPGA or the core won't work
                dir="J_3:31", nxt="J_3:33", stp="J_3:29", rst="J_3:34", rst_invert=True, # USB3320 reset is active low
                attrs=attrs),

            Resource("usb_aux", 1,
                Subsignal("vbus", Pins("J_3:30", dir="i")),
                Subsignal("id",   Pins("J_3:32", dir="o")),
                Subsignal("sbu1", Pins("J_3:45", dir="i")),
                Subsignal("sbu2", Pins("J_3:46", dir="i")),
                attrs),

            ULPIResource("ulpi", 2,
                data="J_3:17 J_3:18 J_3:19 J_3:20 J_3:21 J_3:22 J_3:23 J_3:24",
                clk="J_3:7", clk_dir="o", # this needs to be a clock pin of the FPGA or the core won't work
                dir="J_3:11", nxt="J_3:13", stp="J_3:9", rst="J_3:14", rst_invert=True, # USB3320 reset is active low
                attrs=attrs),

            Resource("usb_aux", 2,
                Subsignal("vbus", Pins("J_3:10", dir="i")),
                Subsignal("id",   Pins("J_3:12", dir="o")),
                Subsignal("sbu1", Pins("J_3:25", dir="i")),
                Subsignal("sbu2", Pins("J_3:26", dir="i")),
                attrs),

            Resource("i2s", 1,
                Subsignal("sclk",   Pins("J_2:53", dir="o")),
                Subsignal("bclk",   Pins("J_2:54", dir="o")),
                Subsignal("data",   Pins("J_2:55", dir="o")),
                Subsignal("lrclk",  Pins("J_2:56", dir="o")),
                attrs),

            Resource("i2s", 2,
                Subsignal("sclk",   Pins("J_2:57", dir="o")),
                Subsignal("bclk",   Pins("J_2:58", dir="o")),
                Subsignal("data",   Pins("J_2:50", dir="o") if colorlight else Pins("J_2:59", dir="o")),
                Subsignal("lrclk",  Pins("J_2:52", dir="o") if colorlight else Pins("J_2:60", dir="o")),
                attrs),


            # TOSLINK
            Resource("toslink", 1,
                Subsignal("tx", Pins("J_2:49", dir="o")),
                Subsignal("rx", Pins("J_2:51", dir="i")),
                attrs),

            Resource("toslink", 2,
                Subsignal("tx", Pins("J_2:33", dir="o")),
                Subsignal("rx", Pins("J_2:35", dir="i")),
                attrs),

            Resource("toslink", 3,
                Subsignal("tx", Pins("J_2:23", dir="o")),
                Subsignal("rx", Pins("J_2:25", dir="i")),
                attrs),

            Resource("toslink", 4,
                Subsignal("tx", Pins("J_2:8", dir="o") if colorlight else Pins("J_2:7", dir="o")),
                Subsignal("rx", Pins("J_2:9", dir="i")),
                attrs),

            # Debug
            SPIResource(0, clk="J_2:12", copi="J_2:8", cipo=None, cs_n="J_2:10", attrs=attrs),

            Resource("debug", 0, Pins("J_2:44", dir="o")),
            Resource("debug", 1, Pins("J_2:46", dir="o")),
            Resource("debug", 2, Pins("J_2:48", dir="o")),
            Resource("debug", 3, Pins("J_2:42", dir="o")),
        ]