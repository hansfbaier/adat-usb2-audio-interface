#!/usr/bin/env python3
import os
import sys
import pickle
from luna.gateware.usb.devices.ila import USBIntegratedLogicAnalyzerFrontend

class ILAData:
    def __init__(self, ila) -> None:
        self.bytes_per_sample = ila.bytes_per_sample
        self.sample_period    = ila.sample_period
        self.sample_depth     = ila.sample_depth
        self.sample_rate      = ila.sample_rate
        self.sample_width     = ila.sample_width
        self.signals          = ila.signals

sys.setrecursionlimit(15000)
ila = pickle.load(open("ila.P", "rb"))
print(dir(ila))

if False:
    import usb
    dev=usb.core.find(idVendor=0x1209, idProduct=0x4711)
    print(dev)

frontend = USBIntegratedLogicAnalyzerFrontend(ila=ila, idVendor=0x1209, idProduct=0x4711, endpoint_no=3)
frontend.interactive_display()