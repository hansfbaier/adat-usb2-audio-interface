#!/usr/bin/env python3
#
# Copyright (c) 2021 Hans Baier <hansfbaier@gmail.com>
# SPDX-License-Identifier: CERN-OHL-W-2.0
import os

from nmigen              import *
from nmigen.lib.fifo     import AsyncFIFO
from nmigen.lib.cdc      import FFSynchronizer

from nmigen_library.stream  import connect_stream_to_fifo, connect_fifo_to_stream

from luna                import top_level_cli
from luna.usb2           import USBDevice, USBIsochronousInMemoryEndpoint, USBIsochronousOutStreamEndpoint, USBIsochronousInStreamEndpoint

#from luna.gateware.usb.usb2.endpoints.isochronous import USBIsochronousOutRawStreamEndpoint

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
from requesthandlers        import UAC2RequestHandlers

class USB2AudioInterface(Elaboratable):
    """ USB Audio Class v2 interface """
    NR_CHANNELS = 8
    MAX_PACKET_SIZE = 512 # NR_CHANNELS * 24 + 4
    USE_ILA = False
    ILA_MAX_PACKET_SIZE = 512

    def create_descriptors(self):
        """ Creates the descriptors that describe our audio topology. """

        descriptors = DeviceDescriptorCollection()

        with descriptors.DeviceDescriptor() as d:
            d.bcdUSB             = 2.00
            d.bDeviceClass       = 0xEF
            d.bDeviceSubclass    = 0x02
            d.bDeviceProtocol    = 0x01
            d.idVendor           = 0x1209
            d.idProduct          = 0x4711

            d.iManufacturer      = "OpenAudioGear"
            d.iProduct           = "ADATface"
            d.iSerialNumber      = "4711"
            d.bcdDevice          = 0.01

            d.bNumConfigurations = 1

        with descriptors.ConfigurationDescriptor() as configDescr:
            # Interface Association
            interfaceAssociationDescriptor                 = uac2.InterfaceAssociationDescriptorEmitter()
            interfaceAssociationDescriptor.bInterfaceCount = 3 # Audio Control + Inputs + Outputs
            configDescr.add_subordinate_descriptor(interfaceAssociationDescriptor)

            # Interface Descriptor (Control)
            interfaceDescriptor = uac2.StandardAudioControlInterfaceDescriptorEmitter()
            interfaceDescriptor.bInterfaceNumber = 0
            configDescr.add_subordinate_descriptor(interfaceDescriptor)

            # AudioControl Interface Descriptor
            audioControlInterface = self.create_audio_control_interface_descriptor()
            configDescr.add_subordinate_descriptor(audioControlInterface)

            self.create_output_channels_descriptor(configDescr)

            self.create_input_channels_descriptor(configDescr)

            if self.USE_ILA:
                with configDescr.InterfaceDescriptor() as i:
                    i.bInterfaceNumber = 3

                    with i.EndpointDescriptor() as e:
                        e.bEndpointAddress = USBDirection.IN.to_endpoint_address(3) # EP 3 IN
                        e.wMaxPacketSize   = self.ILA_MAX_PACKET_SIZE

        return descriptors


    def create_audio_control_interface_descriptor(self):
        audioControlInterface = uac2.ClassSpecificAudioControlInterfaceDescriptorEmitter()

        # AudioControl Interface Descriptor (ClockSource)
        clockSource = uac2.ClockSourceDescriptorEmitter()
        clockSource.bClockID     = 1
        clockSource.bmAttributes = uac2.ClockAttributes.INTERNAL_FIXED_CLOCK
        clockSource.bmControls   = uac2.ClockFrequencyControl.HOST_READ_ONLY
        audioControlInterface.add_subordinate_descriptor(clockSource)


        # streaming input port from the host to the USB interface
        inputTerminal               = uac2.InputTerminalDescriptorEmitter()
        inputTerminal.bTerminalID   = 2
        inputTerminal.wTerminalType = uac2.USBTerminalTypes.USB_STREAMING
        # The number of channels needs to be 2 here in order to be recognized
        # default audio out device by Windows. We provide an alternate
        # setting with the full channel count, which also references
        # this terminal ID
        inputTerminal.bNrChannels   = 2
        inputTerminal.bCSourceID    = 1
        audioControlInterface.add_subordinate_descriptor(inputTerminal)

        # audio output port from the USB interface to the outside world
        outputTerminal               = uac2.OutputTerminalDescriptorEmitter()
        outputTerminal.bTerminalID   = 3
        outputTerminal.wTerminalType = uac2.OutputTerminalTypes.SPEAKER
        outputTerminal.bSourceID     = 2
        outputTerminal.bCSourceID    = 1
        audioControlInterface.add_subordinate_descriptor(outputTerminal)

        # audio input port from the outside world to the USB interface
        inputTerminal               = uac2.InputTerminalDescriptorEmitter()
        inputTerminal.bTerminalID   = 4
        inputTerminal.wTerminalType = uac2.InputTerminalTypes.MICROPHONE
        inputTerminal.bNrChannels   = 8
        inputTerminal.bCSourceID    = 1
        audioControlInterface.add_subordinate_descriptor(inputTerminal)

        # audio output port from the USB interface to the host
        outputTerminal               = uac2.OutputTerminalDescriptorEmitter()
        outputTerminal.bTerminalID   = 5
        outputTerminal.wTerminalType = uac2.USBTerminalTypes.USB_STREAMING
        outputTerminal.bSourceID     = 4
        outputTerminal.bCSourceID    = 1
        audioControlInterface.add_subordinate_descriptor(outputTerminal)

        return audioControlInterface


    def create_output_streaming_interface(self, c, *, nr_channels, alt_setting_nr):
        # Interface Descriptor (Streaming, OUT, active setting)
        activeAudioStreamingInterface                   = uac2.AudioStreamingInterfaceDescriptorEmitter()
        activeAudioStreamingInterface.bInterfaceNumber  = 1
        activeAudioStreamingInterface.bAlternateSetting = alt_setting_nr
        activeAudioStreamingInterface.bNumEndpoints     = 2
        c.add_subordinate_descriptor(activeAudioStreamingInterface)

        # AudioStreaming Interface Descriptor (General)
        audioStreamingInterface               = uac2.ClassSpecificAudioStreamingInterfaceDescriptorEmitter()
        audioStreamingInterface.bTerminalLink = 2
        audioStreamingInterface.bFormatType   = uac2.FormatTypes.FORMAT_TYPE_I
        audioStreamingInterface.bmFormats     = uac2.TypeIFormats.PCM
        audioStreamingInterface.bNrChannels   = nr_channels
        c.add_subordinate_descriptor(audioStreamingInterface)

        # AudioStreaming Interface Descriptor (Type I)
        typeIStreamingInterface  = uac2.TypeIFormatTypeDescriptorEmitter()
        typeIStreamingInterface.bSubslotSize   = 4
        typeIStreamingInterface.bBitResolution = 24 # we use all 24 bits
        c.add_subordinate_descriptor(typeIStreamingInterface)

        # Endpoint Descriptor (Audio out)
        audioOutEndpoint = standard.EndpointDescriptorEmitter()
        audioOutEndpoint.bEndpointAddress     = USBDirection.OUT.to_endpoint_address(1) # EP 1 OUT
        audioOutEndpoint.bmAttributes         = USBTransferType.ISOCHRONOUS  | \
                                                (USBSynchronizationType.ASYNC << 2) | \
                                                (USBUsageType.DATA << 4)
        audioOutEndpoint.wMaxPacketSize = self.MAX_PACKET_SIZE
        audioOutEndpoint.bInterval       = 1
        c.add_subordinate_descriptor(audioOutEndpoint)

        # AudioControl Endpoint Descriptor
        audioControlEndpoint = uac2.ClassSpecificAudioStreamingIsochronousAudioDataEndpointDescriptorEmitter()
        c.add_subordinate_descriptor(audioControlEndpoint)

        # Endpoint Descriptor (Feedback IN)
        feedbackInEndpoint = standard.EndpointDescriptorEmitter()
        feedbackInEndpoint.bEndpointAddress  = USBDirection.IN.to_endpoint_address(1) # EP 1 IN
        feedbackInEndpoint.bmAttributes      = USBTransferType.ISOCHRONOUS  | \
                                               (USBSynchronizationType.NONE << 2)  | \
                                               (USBUsageType.FEEDBACK << 4)
        feedbackInEndpoint.wMaxPacketSize    = 4
        feedbackInEndpoint.bInterval         = 4
        c.add_subordinate_descriptor(feedbackInEndpoint)


    def create_output_channels_descriptor(self, c):
        #
        # Interface Descriptor (Streaming, OUT, quiet setting)
        #
        quietAudioStreamingInterface = uac2.AudioStreamingInterfaceDescriptorEmitter()
        quietAudioStreamingInterface.bInterfaceNumber  = 1
        quietAudioStreamingInterface.bAlternateSetting = 0
        c.add_subordinate_descriptor(quietAudioStreamingInterface)

        # we need the default alternate setting to be stereo
        # out for windows to automatically recognize
        # and use this audio interface
        self.create_output_streaming_interface(c, nr_channels=2, alt_setting_nr=1)
        self.create_output_streaming_interface(c, nr_channels=self.NR_CHANNELS, alt_setting_nr=2)


    def create_input_streaming_interface(self, c, *, nr_channels, alt_setting_nr, channel_config=0):
        # Interface Descriptor (Streaming, IN, active setting)
        activeAudioStreamingInterface = uac2.AudioStreamingInterfaceDescriptorEmitter()
        activeAudioStreamingInterface.bInterfaceNumber  = 2
        activeAudioStreamingInterface.bAlternateSetting = alt_setting_nr
        activeAudioStreamingInterface.bNumEndpoints     = 1
        c.add_subordinate_descriptor(activeAudioStreamingInterface)

        # AudioStreaming Interface Descriptor (General)
        audioStreamingInterface                 = uac2.ClassSpecificAudioStreamingInterfaceDescriptorEmitter()
        audioStreamingInterface.bTerminalLink   = 5
        audioStreamingInterface.bFormatType     = uac2.FormatTypes.FORMAT_TYPE_I
        audioStreamingInterface.bmFormats       = uac2.TypeIFormats.PCM
        audioStreamingInterface.bNrChannels     = nr_channels
        audioStreamingInterface.bmChannelConfig = channel_config
        c.add_subordinate_descriptor(audioStreamingInterface)

        # AudioStreaming Interface Descriptor (Type I)
        typeIStreamingInterface  = uac2.TypeIFormatTypeDescriptorEmitter()
        typeIStreamingInterface.bSubslotSize   = 4
        typeIStreamingInterface.bBitResolution = 24 # we use all 24 bits
        c.add_subordinate_descriptor(typeIStreamingInterface)

        # Endpoint Descriptor (Audio out)
        audioOutEndpoint = standard.EndpointDescriptorEmitter()
        audioOutEndpoint.bEndpointAddress     = USBDirection.IN.to_endpoint_address(2) # EP 2 IN
        audioOutEndpoint.bmAttributes         = USBTransferType.ISOCHRONOUS  | \
                                                (USBSynchronizationType.ASYNC << 2) | \
                                                (USBUsageType.DATA << 4)
        audioOutEndpoint.wMaxPacketSize = self.MAX_PACKET_SIZE
        audioOutEndpoint.bInterval      = 1
        c.add_subordinate_descriptor(audioOutEndpoint)

        # AudioControl Endpoint Descriptor
        audioControlEndpoint = uac2.ClassSpecificAudioStreamingIsochronousAudioDataEndpointDescriptorEmitter()
        c.add_subordinate_descriptor(audioControlEndpoint)


    def create_input_channels_descriptor(self, c):
        #
        # Interface Descriptor (Streaming, IN, quiet setting)
        #
        quietAudioStreamingInterface = uac2.AudioStreamingInterfaceDescriptorEmitter()
        quietAudioStreamingInterface.bInterfaceNumber  = 2
        quietAudioStreamingInterface.bAlternateSetting = 0
        c.add_subordinate_descriptor(quietAudioStreamingInterface)

        # Windows wants a stereo pair as default setting, so let's have it
        self.create_input_streaming_interface(c, nr_channels=2, alt_setting_nr=1, channel_config=0x3)
        self.create_input_streaming_interface(c, nr_channels=self.NR_CHANNELS, alt_setting_nr=2, channel_config=0x0)


    def elaborate(self, platform):
        m = Module()

        # Generate our domain clocks/resets.
        m.submodules.car = platform.clock_domain_generator()

        # Create our USB-to-serial converter.
        ulpi = platform.request(platform.default_usb_connection)
        m.submodules.usb = usb = USBDevice(bus=ulpi)

        # Add our standard control endpoint to the device.
        descriptors = self.create_descriptors()
        control_ep = usb.add_control_endpoint()
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

        ep1_out = USBIsochronousOutStreamEndpoint(
            endpoint_number=1, # EP 1 OUT
            max_packet_size=self.MAX_PACKET_SIZE)
        usb.add_endpoint(ep1_out)

        ep1_in = USBIsochronousInMemoryEndpoint(
            endpoint_number=1, # EP 1 IN
            max_packet_size=4)
        usb.add_endpoint(ep1_in)

        ep2_in = USBIsochronousInMemoryEndpoint(
            endpoint_number=2, # EP 2 IN
            max_packet_size=self.MAX_PACKET_SIZE)
        usb.add_endpoint(ep2_in)

        # calculate bytes in frame for audio in
        audio_in_frame_bytes = Signal(range(self.MAX_PACKET_SIZE), reset=24 * self.NR_CHANNELS)
        audio_in_frame_bytes_counting = Signal()

        with m.If(audio_in_frame_bytes_counting):
            m.d.usb += audio_in_frame_bytes.eq(audio_in_frame_bytes + 1)

        with m.If(ep1_out.stream.valid & ep1_out.stream.ready):
            with m.If(ep1_out.stream.first):
                m.d.usb += [
                    audio_in_frame_bytes.eq(1),
                    audio_in_frame_bytes_counting.eq(1),
                ]
            with m.Elif(ep1_out.stream.last):
                m.d.usb += audio_in_frame_bytes_counting.eq(0)

        # Connect our device as a high speed device
        m.d.comb += [
            ep1_in.bytes_in_frame.eq(4),
            ep2_in.bytes_in_frame.eq(audio_in_frame_bytes),
            usb.connect          .eq(1),
            usb.full_speed_only  .eq(0),
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

        with m.If(usb.sof_detected):
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
            bitPos.eq(ep1_in.address << 3),
            ep1_in.value.eq(0xff & (feedbackValue >> bitPos)),
            ep2_in.value.eq(ep2_in.address),
        ]

        m.submodules.usb_to_channel_stream = usb_to_channel_stream = \
            DomainRenamer("usb")(USBStreamToChannels(self.NR_CHANNELS))

        num_channels = Signal(range(self.NR_CHANNELS * 2), reset=2)
        m.d.comb += usb_to_channel_stream.no_channels_in.eq(num_channels)

        with m.Switch(class_request_handler.output_interface_altsetting_nr):
            with m.Case(2):
                m.d.usb += num_channels.eq(8)
            with m.Default():
                m.d.usb += num_channels.eq(2)

        nr_channel_bits = Shape.cast(range(self.NR_CHANNELS)).width
        m.submodules.usb_to_adat_fifo = usb_to_adat_fifo = \
            AsyncFIFO(width=24 + nr_channel_bits + 2, depth=64, w_domain="usb", r_domain="sync")

        m.submodules.adat_transmitter = adat_transmitter = ADATTransmitter(fifo_depth=4)
        #m.submodules.adat_receiver    = adat_receiver    = ADATReceiver()

        adat = platform.request("adat")

        m.d.comb += [
            # wire USB to FIFO
            usb_to_channel_stream.usb_stream_in.stream_eq(ep1_out.stream),
            *connect_stream_to_fifo(usb_to_channel_stream.channel_stream_out, usb_to_adat_fifo),

            usb_to_adat_fifo.w_data[24:(24 + nr_channel_bits)]
                .eq(usb_to_channel_stream.channel_stream_out.channel_no),

            usb_to_adat_fifo.w_data[(24 + nr_channel_bits)]
                .eq(usb_to_channel_stream.channel_stream_out.first),

            usb_to_adat_fifo.w_data[(24 + nr_channel_bits + 1)]
                .eq(usb_to_channel_stream.channel_stream_out.last),

            usb_to_adat_fifo.r_en.eq(adat_transmitter.ready_out),

            # wire FIFO to ADAT transmitter
            adat_transmitter.sample_in    .eq(usb_to_adat_fifo.r_data[0:24]),
            adat_transmitter.addr_in      .eq(usb_to_adat_fifo.r_data[24:(24 + nr_channel_bits)]),
            adat_transmitter.last_in      .eq(usb_to_adat_fifo.r_data[-1]),
            adat_transmitter.valid_in     .eq(usb_to_adat_fifo.r_rdy & usb_to_adat_fifo.r_en),
            adat_transmitter.user_data_in .eq(0),

            # ADAT output
            adat.tx.eq(adat_transmitter.adat_out)
        ]

        if self.USE_ILA:
            adat_clock = Signal()
            m.d.comb += adat_clock.eq(ClockSignal("adat"))
            sof_wrap = Signal()
            m.d.comb += sof_wrap.eq(sof_counter == 0)

            signals = [
                usb.sof_detected,
                #ep1_out.stream.valid,
                #ep1_out.stream.ready,
                #ep1_out.stream.payload,
                #ep1_out.stream.first,
                #ep1_out.stream.last,
                #usb_to_channel_stream_in.valid,
                #usb_to_channel_stream_in.ready,
                #usb_to_channel_stream_in.payload,
                #usb_to_channel_stream_in.first,
                class_request_handler.interface_settings_changed,
                class_request_handler.output_interface_altsetting_nr,
                num_channels,
                usb_to_channel_stream.usb_stream_in.last,
                #usb_to_channel_stream.channel_stream_out.valid,
                #usb_to_channel_stream.channel_stream_out.payload,
                #usb_to_channel_stream.channel_stream_out.last,
                #usb_to_channel_stream.channel_stream_out.channel_no,
                usb_to_adat_fifo.r_level,
                #usb_to_adat_fifo.r_rdy,
                adat_transmitter.valid_in,
                adat_transmitter.ready_out,
                #adat_transmitter.addr_in,
                adat_transmitter.last_in,
                #adat_transmitter.sample_in,
                #adat_transmitter.fifo_level_out,
                adat_transmitter.frame_out,
                adat_transmitter.underflow_out,
                #adat_transmitter.adat_out,
            ]

            signals_bits = sum([s.width for s in signals])
            depth = int(33*8*1024/signals_bits)
            m.submodules.ila = ila = \
                StreamILA(
                    signals=signals,
                    sample_depth=depth,
                    domain="usb", o_domain="usb",
                    samples_pretrigger=512)

            stream_ep = USBMultibyteStreamInEndpoint(
                endpoint_number=3, # EP 3 IN
                max_packet_size=self.ILA_MAX_PACKET_SIZE,
                byte_width=ila.bytes_per_sample
            )
            usb.add_endpoint(stream_ep)

            m.d.comb += [
                stream_ep.stream.stream_eq(ila.stream),
                ila.trigger.eq(adat_transmitter.underflow_out),
            ]

            ILACoreParameters(ila).pickle()

        led = platform.request("debug_led")
        m.d.comb += [
            led[0].eq(usb.tx_activity_led),
            led[1].eq(usb.rx_activity_led),
            led[2].eq(usb.suspended),
            led[3].eq(usb.reset_detected),
            led[4].eq(adat_transmitter.underflow_out),
        ]

        return m

if __name__ == "__main__":
    os.environ["LUNA_PLATFORM"] = "qmtech_ep4ce15_platform:ADATFacePlatform"
    #os.environ["LUNA_PLATFORM"] = "tinybx_luna:TinyBxAdatPlatform"
    top_level_cli(USB2AudioInterface)