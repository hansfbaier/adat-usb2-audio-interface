#!/usr/bin/env python3
from channels_to_usb_stream import ChannelsToUSBStream
from nmigen.sim import Simulator, Tick

if __name__ == "__main__":
    dut = ChannelsToUSBStream(8)

    def send_one_frame(sample: int, channel: int, wait=True):
        yield dut.channel_stream_in.channel_nr.eq(channel)
        yield dut.channel_stream_in.payload.eq(sample)
        yield dut.channel_stream_in.valid.eq(1)
        yield
        if wait:
            yield
            yield
            yield

    def process():
        yield dut.usb_stream_out.ready.eq(0)
        yield dut.frame_finished_in.eq(1)
        yield
        yield dut.frame_finished_in.eq(0)
        yield
        yield
        yield
        yield
        yield
        yield
        yield dut.usb_stream_out.ready.eq(1)
        yield from send_one_frame(0x030201, 0, wait=False)
        yield from send_one_frame(0x131211, 1)
        yield from send_one_frame(0x232221, 2)
        yield from send_one_frame(0x333231, 3)
        # source stream stalls, see if we wait
        yield dut.channel_stream_in.valid.eq(0)
        for _ in range(7): yield
        yield from send_one_frame(0x434241, 4)
        yield from send_one_frame(0x535251, 5)
        yield from send_one_frame(0x636261, 6)
        yield from send_one_frame(0x737271, 7, wait=False)
        # out stream quits early, see if it
        # consumes extraneous bytes
        yield dut.usb_stream_out.ready.eq(0)
        yield
        for _ in range(15): yield
        yield dut.frame_finished_in.eq(1)
        yield
        yield dut.frame_finished_in.eq(0)
        for _ in range(35): yield
        yield from send_one_frame(0x030201, 0)
        yield from send_one_frame(0x131211, 1)
        yield dut.usb_stream_out.ready.eq(1)
        yield from send_one_frame(0x232221, 2)
        yield from send_one_frame(0x333231, 3)
        yield from send_one_frame(0x434241, 4)
        yield from send_one_frame(0x535251, 5)
        yield from send_one_frame(0x636261, 6)
        yield from send_one_frame(0x737271, 7)
        yield dut.channel_stream_in.valid.eq(0)
        yield
        for _ in range(45): yield

    sim = Simulator(dut)
    sim.add_clock(1.0/60e6,)
    sim.add_sync_process(process)

    with sim.write_vcd(f'channels_to_usb_stream.vcd'):
        sim.run()