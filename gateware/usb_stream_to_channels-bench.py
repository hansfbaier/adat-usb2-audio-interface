#!/usr/bin/env python3
from usb_stream_to_channels import USBStreamToChannels
from nmigen.sim import Simulator, Tick

if __name__ == "__main__":
    dut = USBStreamToChannels(8)

    def send_one_frame():
        data = [n % 4 + (n//4 << 4) for n in range(24)]
        yield dut.usb_stream.valid.eq(1)
        yield dut.usb_stream.first.eq(1)
        for byte in data:
            yield dut.usb_stream.payload.eq(byte)
            yield Tick("usb")
            yield dut.usb_stream.first.eq(0)
        yield dut.usb_stream.last.eq(1)
        yield dut.usb_stream.valid.eq(0)
        yield Tick("usb")
        yield dut.usb_stream.last.eq(0)

    def usb_process():
        yield dut.usb_stream.payload.eq(0xff)
        yield Tick("usb")
        yield from send_one_frame()
        yield Tick("usb")
        yield Tick("usb")
        yield from send_one_frame()
        yield from send_one_frame()
        yield Tick("usb")
        yield Tick("usb")

    sim = Simulator(dut)
    sim.add_clock(1.0/60e6, domain="usb")
    sim.add_sync_process(usb_process, domain="usb")

    with sim.write_vcd(f'usb_stream_to_channels.vcd'):
        sim.run()