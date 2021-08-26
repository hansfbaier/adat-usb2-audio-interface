"""
use the LUNA usb config for the tinyFPGA-Bx
add some pins (at random) for adat and debug
create an audio clock domain

Issues:
The audio clock is just a carbon copy of usb 12MHz because the Bx only has one PLL.

"""

import os
import logging
import subprocess

from nmigen import *
from nmigen.build import *
from nmigen_boards.resources import *

from luna.gateware.platform.tinyfpga import TinyFPGABxPlatform, TinyFPGABxDomainGenerator


class TinyBxAdatDomainGenerator(Elaboratable):
  """ Creates audio clock domains on top of the LUNA domains for the TinyFPGA Bx. """

  def elaborate(self, platform):
    m = TinyFPGABxDomainGenerator.elaborate(self, platform)

    # Create our domains...
    m.domains.adat = ClockDomain()
    m.d.comb += [
      ClockSignal("adat").eq(ClockSignal("usb")),
      ResetSignal("adat").eq(ResetSignal("usb")),
    ]

    return m


class TinyBxAdatPlatform(TinyFPGABxPlatform):
  clock_domain_generator = TinyBxAdatDomainGenerator
  number_of_channels = 4
  bitwidth           = 24

  def __init__(self):
    self.resources += [
      Resource("adat", 0,
        Subsignal("tx", Pins("A2", dir="o")),
        Subsignal("rx", Pins("A1", dir="i")),
        Attrs(IO_STANDARD="SB_LVCMOS")),

      Resource("debug_led", 0, Pins("C9 A9 B8 A8 B7 A7 B6 A6", dir="o"),
        Attrs(IO_STANDARD="SB_LVCMOS")),
    ]
    super().__init__(toolchain="IceStorm")



