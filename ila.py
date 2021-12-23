#!/usr/bin/env python3
import usb
from luna.gateware.usb.devices.ila  import USBIntegratedLogicAnalyzerFrontend
from amaranth_library.debug.ila     import ILACoreParameters


dev=usb.core.find(idVendor=0x1209, idProduct=0xADA1)
print(dev)

frontend = USBIntegratedLogicAnalyzerFrontend(ila=ILACoreParameters.unpickle(), idVendor=0x1209, idProduct=0xADA1, endpoint_no=3)
frontend.interactive_display()
