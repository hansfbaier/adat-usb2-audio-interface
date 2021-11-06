#!/usr/bin/env python3
#
# Copyright (c) 2021 Hans Baier <hansfbaier@gmail.com>
# SPDX-License-Identifier: CERN-OHL-W-2.0
import os

from nmigen              import *
from nmigen.lib.fifo     import AsyncFIFO
from nmigen.lib.cdc      import FFSynchronizer

from nmigen_library.stream       import connect_stream_to_fifo
from nmigen_library.io.i2s       import I2STransmitter
from nmigen_library.io.max7219   import SerialLEDArray, NumberToSevenSegmentHex

from luna                import top_level_cli
from luna.usb2           import USBDevice, USBIsochronousInMemoryEndpoint, USBIsochronousOutStreamEndpoint, USBIsochronousInStreamEndpoint

from usb_protocol.types                       import USBRequestType, USBRequestRecipient, USBTransferType, USBSynchronizationType, USBUsageType, USBDirection, USBStandardRequests
from usb_protocol.types.descriptors.uac2      import AudioClassSpecificRequestCodes
from usb_protocol.emitters                    import DeviceDescriptorCollection
from usb_protocol.emitters.descriptors        import uac2, standard

from luna.gateware.platform                   import NullPin
from luna.gateware.usb.usb2.device            import USBDevice
from luna.gateware.usb.usb2.endpoints.stream  import USBMultibyteStreamInEndpoint
from luna.gateware.usb.usb2.request           import USBRequestHandler, StallOnlyRequestHandler
from luna.gateware.debug.ila                  import StreamILA, ILACoreParameters

from adat import ADATTransmitter, ADATReceiver
from adat import EdgeToPulse

from usb_stream_to_channels import USBStreamToChannels
from channels_to_usb_stream import ChannelsToUSBStream
from requesthandlers        import UAC2RequestHandlers

from usb_descriptors import USBDescriptors

class USB2AudioInterface(Elaboratable):
    """ USB Audio Class v2 interface """
    number_of_channels = 8
    bitwidth           = 24
    MAX_PACKET_SIZE    = 256
    USE_ILA = False
    ILA_MAX_PACKET_SIZE = 512

    def elaborate(self, platform):
        m = Module()

        self.number_of_channels = platform.number_of_channels
        self.bitwidth           = platform.bitwidth

        # Generate our domain clocks/resets.
        m.submodules.car = platform.clock_domain_generator()

        # Create our USB-to-serial converter.
        ulpi1 = platform.request("ulpi", 1)
        m.submodules.usb1 = usb1 = USBDevice(bus=ulpi1)

        # Add our standard control endpoint to the device.
        descriptors = USBDescriptors(max_packet_size=self.MAX_PACKET_SIZE, number_of_channels=self.number_of_channels, use_ila=self.USE_ILA).create_descriptors()
        control_ep = usb1.add_control_endpoint()
        control_ep.add_standard_request_handlers(descriptors, blacklist=[
            lambda setup:   (setup.type    == USBRequestType.STANDARD)
                          & (setup.request == USBStandardRequests.SET_INTERFACE)
        ])

        # Attach our class request handlers.
        class_request_handler = UAC2RequestHandlers()
        control_ep.add_request_handler(class_request_handler)

        # Attach class-request handlers that stall any vendor or reserved requests,
        # as we don't have or need any.
        stall_condition = lambda setup : \
            (setup.type == USBRequestType.VENDOR) | \
            (setup.type == USBRequestType.RESERVED)
        control_ep.add_request_handler(StallOnlyRequestHandler(stall_condition))

        usb1_ep1_out = USBIsochronousOutStreamEndpoint(
            endpoint_number=1, # EP 1 OUT
            max_packet_size=self.MAX_PACKET_SIZE)
        usb1.add_endpoint(usb1_ep1_out)

        usb1_ep1_in = USBIsochronousInMemoryEndpoint(
            endpoint_number=1, # EP 1 IN
            max_packet_size=4)
        usb1.add_endpoint(usb1_ep1_in)

        usb1_ep2_in = USBIsochronousInStreamEndpoint(
            endpoint_number=2, # EP 2 IN
            max_packet_size=self.MAX_PACKET_SIZE)
        usb1.add_endpoint(usb1_ep2_in)

        # calculate bytes in frame for audio in
        audio_in_frame_bytes = Signal(range(self.MAX_PACKET_SIZE), reset=24 * self.number_of_channels)
        audio_in_frame_bytes_counting = Signal()

        with m.If(usb1_ep1_out.stream.valid & usb1_ep1_out.stream.ready):
            with m.If(audio_in_frame_bytes_counting):
                m.d.usb += audio_in_frame_bytes.eq(audio_in_frame_bytes + 1)

            with m.If(usb1_ep1_out.stream.first):
                m.d.usb += [
                    audio_in_frame_bytes.eq(1),
                    audio_in_frame_bytes_counting.eq(1),
                ]
            with m.Elif(usb1_ep1_out.stream.last):
                m.d.usb += audio_in_frame_bytes_counting.eq(0)

        # Connect our device as a high speed device
        m.d.comb += [
            usb1_ep1_in.bytes_in_frame.eq(4),
            usb1_ep2_in.bytes_in_frame.eq(audio_in_frame_bytes),
            usb1.connect          .eq(1),
            usb1.full_speed_only  .eq(0),
        ]

        # feedback endpoint
        feedbackValue      = Signal(32, reset=0x60000)
        bitPos             = Signal(5)

        # this tracks the number of ADAT frames since the last USB frame
        # 12.288MHz / 8kHz = 1536, so we need at least 11 bits = 2048
        # we need to capture 32 micro frames to get to the precision
        # required by the USB standard, so and that is 0xc000, so we
        # need 16 bits here
        adat_clock_counter = Signal(16)
        sof_counter        = Signal(5)

        adat_clock_usb = Signal()
        m.submodules.adat_clock_usb_sync = FFSynchronizer(ClockSignal("adat"), adat_clock_usb, o_domain="usb")
        m.submodules.adat_clock_usb_pulse = adat_clock_usb_pulse = DomainRenamer("usb")(EdgeToPulse())
        adat_clock_tick = Signal()
        m.d.usb += [
            adat_clock_usb_pulse.edge_in.eq(adat_clock_usb),
            adat_clock_tick.eq(adat_clock_usb_pulse.pulse_out),
        ]

        with m.If(adat_clock_tick):
            m.d.usb += adat_clock_counter.eq(adat_clock_counter + 1)

        with m.If(usb1.sof_detected):
            m.d.usb += sof_counter.eq(sof_counter + 1)

            # according to USB2 standard chapter 5.12.4.2
            # we need 2**13 / 2**8 = 2**5 = 32 SOF-frames of
            # sample master frequency counter to get enough
            # precision for the sample frequency estimate
            # / 2**8 because the ADAT-clock = 256 times = 2**8
            # the sample frequency and sof_counter is 5 bits
            # so it wraps automatically every 32 SOFs
            with m.If(sof_counter == 0):
                m.d.usb += [
                    feedbackValue.eq(adat_clock_counter << 3),
                    adat_clock_counter.eq(0),
                ]

        m.d.comb += [
            bitPos.eq(usb1_ep1_in.address << 3),
            usb1_ep1_in.value.eq(0xff & (feedbackValue >> bitPos)),
        ]

        m.submodules.usb1_to_channel_stream = usb1_to_channel_stream = \
            DomainRenamer("usb")(USBStreamToChannels(self.number_of_channels))

        m.submodules.channels_to_usb1_stream = channels_to_usb1_stream = \
            DomainRenamer("usb")(ChannelsToUSBStream(self.number_of_channels, max_packet_size=self.MAX_PACKET_SIZE))

        num_channels = Signal(range(self.number_of_channels * 2), reset=2)
        m.d.comb += usb1_to_channel_stream.no_channels_in.eq(num_channels)

        with m.Switch(class_request_handler.output_interface_altsetting_nr):
            with m.Case(2):
                m.d.usb += num_channels.eq(8)
            with m.Default():
                m.d.usb += num_channels.eq(2)

        nr_channel_bits = Shape.cast(range(self.number_of_channels)).width
        m.submodules.usb1_to_adat_fifo = usb1_to_adat_fifo = \
            AsyncFIFO(width=24 + nr_channel_bits + 2, depth=64, w_domain="usb", r_domain="sync")

        m.submodules.adat_to_usb1_fifo = adat_to_usb1_fifo = \
            AsyncFIFO(width=24 + nr_channel_bits + 2, depth=64, w_domain="fast", r_domain="usb")

        m.submodules.adat1_transmitter = adat1_transmitter = ADATTransmitter(fifo_depth=4)
        m.submodules.adat1_receiver    = adat1_receiver    = DomainRenamer("fast")(ADATReceiver(int(100e6)))
        adat1_pads = platform.request("toslink", 1)

        m.submodules.dac1_transmitter = dac1 = DomainRenamer("usb")(I2STransmitter(sample_width=24))
        m.submodules.dac2_transmitter = dac2 = DomainRenamer("usb")(I2STransmitter(sample_width=24))
        dac1_pads = platform.request("i2s", 1)
        dac2_pads = platform.request("i2s", 2)

        m.d.comb += [
            # convert USB stream to audio stream
            usb1_to_channel_stream.usb_stream_in.stream_eq(usb1_ep1_out.stream),
            *connect_stream_to_fifo(usb1_to_channel_stream.channel_stream_out, usb1_to_adat_fifo),

            usb1_to_adat_fifo.w_data[24:(24 + nr_channel_bits)]
                .eq(usb1_to_channel_stream.channel_stream_out.channel_nr),

            usb1_to_adat_fifo.w_data[(24 + nr_channel_bits)]
                .eq(usb1_to_channel_stream.channel_stream_out.first),

            usb1_to_adat_fifo.w_data[(24 + nr_channel_bits + 1)]
                .eq(usb1_to_channel_stream.channel_stream_out.last),

            usb1_to_adat_fifo.r_en.eq(adat1_transmitter.ready_out),

            # wire transmit FIFO to ADAT transmitter
            adat1_transmitter.sample_in    .eq(usb1_to_adat_fifo.r_data[0:24]),
            adat1_transmitter.addr_in      .eq(usb1_to_adat_fifo.r_data[24:(24 + nr_channel_bits)]),
            adat1_transmitter.last_in      .eq(usb1_to_adat_fifo.r_data[-1]),
            adat1_transmitter.valid_in     .eq(usb1_to_adat_fifo.r_rdy & usb1_to_adat_fifo.r_en),
            adat1_transmitter.user_data_in .eq(0),

            # ADAT output
            adat1_pads.tx.eq(adat1_transmitter.adat_out),

            # ADAT input
            adat1_receiver.adat_in.eq(adat1_pads.rx),

            # wire up receive FIFO to ADAT receiver
            adat_to_usb1_fifo.w_data[0:24]  .eq(adat1_receiver.sample_out),
            adat_to_usb1_fifo.w_data[24:27] .eq(adat1_receiver.addr_out),
            adat_to_usb1_fifo.w_en          .eq(adat1_receiver.output_enable),

            # convert audio stream to USB stream
            channels_to_usb1_stream.channel_stream_in.payload.eq(adat_to_usb1_fifo.r_data[0:24]),
            channels_to_usb1_stream.channel_stream_in.channel_nr.eq(adat_to_usb1_fifo.r_data[24:27]),
            channels_to_usb1_stream.channel_stream_in.valid.eq(adat_to_usb1_fifo.r_rdy),
            channels_to_usb1_stream.data_requested_in.eq(usb1_ep2_in.data_requested),
            channels_to_usb1_stream.frame_finished_in.eq(usb1_ep2_in.frame_finished),
            adat_to_usb1_fifo.r_en.eq(channels_to_usb1_stream.channel_stream_in.ready),

            # wire up USB audio IN
            usb1_ep2_in.stream.stream_eq(channels_to_usb1_stream.usb_stream_out),
        ]

        if self.USE_ILA:
            adat_clock = Signal()
            m.d.comb += adat_clock.eq(ClockSignal("adat"))
            sof_wrap = Signal()
            m.d.comb += sof_wrap.eq(sof_counter == 0)

            usb_valid = Signal()
            usb_ready = Signal()
            in_payload = Signal()

            m.d.comb += [
                usb_valid.eq(usb1_ep2_in.stream.valid),
                usb_ready.eq(usb1_ep2_in.stream.ready),
                in_payload.eq(usb1_ep2_in.stream.payload),
            ]

            signals = [
                channels_to_usb1_stream.channel_stream_in.channel_nr,
                channels_to_usb1_stream.level,
                channels_to_usb1_stream.out_channel,
                audio_in_frame_bytes,
                usb1_ep2_in.data_requested,
                usb1_ep2_in.frame_finished,
                channels_to_usb1_stream.done,
                channels_to_usb1_stream.skipping,
                channels_to_usb1_stream.filling,
                channels_to_usb1_stream.channel_mismatch,
                usb_valid,
                usb_ready,
            ]

            signals_bits = sum([s.width for s in signals])
            depth = int(20*8*1024/signals_bits)
            m.submodules.ila = ila = \
                StreamILA(
                    signals=signals,
                    sample_depth=depth,
                    domain="usb", o_domain="usb",
                    samples_pretrigger=256)

            stream_ep = USBMultibyteStreamInEndpoint(
                endpoint_number=3, # EP 3 IN
                max_packet_size=self.ILA_MAX_PACKET_SIZE,
                byte_width=ila.bytes_per_sample
            )
            usb1.add_endpoint(stream_ep)

            m.d.comb += [
                stream_ep.stream.stream_eq(ila.stream),
                ila.trigger.eq(channels_to_usb1_stream.channel_mismatch),
            ]

            ILACoreParameters(ila).pickle()

        usb_aux1 = platform.request("usb_aux", 1)
        usb_aux2 = platform.request("usb_aux", 2)
        leds = platform.request("leds")
        m.d.comb += [
            leds.active1.eq(usb1.tx_activity_led | usb1.rx_activity_led),
            leds.suspended1.eq(usb1.suspended),
            leds.active2.eq(0),
            leds.suspended2.eq(0),
            leds.usb1.eq(usb_aux1.vbus),
            leds.usb2.eq(usb_aux2.vbus),
        ]

        # DEBUG display

        adat1_underflow_count = Signal(16)

        with m.If(~usb1.suspended & adat1_transmitter.underflow_out):
            m.d.sync += adat1_underflow_count.eq(adat1_underflow_count + 1)

        spi = platform.request("spi")
        m.submodules.sevensegment = sevensegment = DomainRenamer("usb")(NumberToSevenSegmentHex(width=32))
        m.submodules.led_display  = led_display  = DomainRenamer("usb")(SerialLEDArray(divisor=10, init_delay=24e6))
        m.d.comb += [
            sevensegment.number_in[0:16].eq(adat1_underflow_count),
            sevensegment.dots_in.eq(leds),
            *led_display.connect_to_resource(spi),
            Cat(led_display.digits_in).eq(sevensegment.seven_segment_out),
            led_display.valid_in.eq(1),
        ]

        return m

if __name__ == "__main__":
    os.environ["LUNA_PLATFORM"] = "qmtech_ep4ce_platform:ADATFacePlatform"
    #os.environ["LUNA_PLATFORM"] = "qmtech_10cl006_platform:ADATFacePlatform"
    top_level_cli(USB2AudioInterface)