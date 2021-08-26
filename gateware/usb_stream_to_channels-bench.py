#!/usr/bin/env python3
from usb_stream_to_channels import USBStreamToChannels
from nmigen.sim import Simulator, Tick

if __name__ == "__main__":
    dut = USBStreamToChannels(8)

    def send_one_frame(seamless=False, drop_valid=False, drop_ready=False):
        data = [n % 4 + (n//4 << 4) for n in range(32)]
        yield dut.usb_stream_in.valid.eq(1)
        yield dut.usb_stream_in.first.eq(1)
        yield dut.channel_stream_out.ready.eq(1)
        for pos, byte in enumerate(data):
            yield dut.usb_stream_in.payload.eq(byte)
            yield Tick()
            yield dut.usb_stream_in.first.eq(0)
            if drop_valid and pos == 7 * 4 + 2:
                yield dut.usb_stream_in.valid.eq(0)
                for _ in range(4): yield Tick()
                yield dut.usb_stream_in.valid.eq(1)
            if drop_ready and pos == 7 * 2 + 3:
                yield dut.channel_stream_out.ready.eq(0)
                for _ in range(7): yield Tick()
                yield dut.channel_stream_out.ready.eq(1)
        yield dut.usb_stream_in.last.eq(1)
        yield dut.usb_stream_in.valid.eq(0)
        if not seamless:
            for _ in range(10): yield Tick()
            yield dut.usb_stream_in.first.eq(1)
            yield dut.usb_stream_in.payload.eq(data[0])
        yield dut.usb_stream_in.last.eq(0)

    def process():
        yield dut.usb_stream_in.payload.eq(0xff)
        yield Tick()
        yield from send_one_frame()
        yield Tick()
        yield Tick()
        yield from send_one_frame(seamless=True, drop_valid=True)
        yield from send_one_frame(seamless=True, drop_ready=True)
        for _ in range(5): yield Tick()

    sim = Simulator(dut)
    sim.add_clock(1.0/60e6,)
    sim.add_sync_process(process)

    with sim.write_vcd(f'usb_stream_to_channels.vcd'):
        sim.run()