#!/usr/bin/env python3
#
# Copyright (c) 2021 Hans Baier <hansfbaier@gmail.com>
# SPDX-License-Identifier: CERN-OHL-W-2.0

import os

from nmigen              import Elaboratable, Module, Cat

from luna                import top_level_cli
from luna.usb2           import USBDevice, USBIsochronousInEndpoint, USBIsochronousOutEndpoint

from luna.gateware.platform                      import NullPin
from luna.gateware.platform.de0_nano             import DE0NanoPlatform
from luna.gateware.usb.usb2.device               import USBDevice
from luna.gateware.usb.usb2.request              import USBRequestHandler, StallOnlyRequestHandler
from luna.gateware.usb.usb2.endpoints.stream     import USBStreamInEndpoint, USBStreamOutEndpoint

from luna.gateware.usb.stream        import USBInStreamInterface
from luna.gateware.stream.generator  import StreamSerializer
from nmigen.hdl.ast import Const

from usb_protocol.types                  import USBRequestType, USBTransferType, USBSynchronizationType, USBUsageType, USBDirection, USBStandardRequests
from usb_protocol.types.descriptors.uac2 import AudioClassSpecificRequestCodes
from usb_protocol.emitters               import DeviceDescriptorCollection
from usb_protocol.emitters.descriptors   import uac2, standard

class USB2AudioInterface(Elaboratable):
    """ USB Audio Class v2 interface """
    MAX_PACKET_SIZE = 256 * 3 # 256 samples of 24 bit each

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
            interfaceDescriptor.bInterfaceNumber = 1
            configDescr.add_subordinate_descriptor(interfaceDescriptor)

            # AudioControl Interface Descriptor
            audioControlInterface = self.create_audio_control_interface_descriptor()
            configDescr.add_subordinate_descriptor(audioControlInterface)

            self.create_output_channels_descriptor(configDescr)

            self.create_input_channels_descriptor(configDescr)

        return descriptors

    def create_audio_control_interface_descriptor(self):
        audioControlInterface = uac2.ClassSpecificAudioControlInterfaceDescriptorEmitter()

        # AudioControl Interface Descriptor (ClockSource)
        clockSource = uac2.ClockSourceDescriptorEmitter()
        clockSource.bClockID     = 1
        clockSource.bmAttributes = uac2.ClockAttributes.INTERNAL_FIXED_CLOCK
        clockSource.bmControls   = uac2.ClockFrequencyControl.HOST_READ_ONLY
        audioControlInterface.add_subordinate_descriptor(clockSource)

        # AudioControl Interface Descriptor (InputTerminal)
        inputTerminal               = uac2.InputTerminalDescriptorEmitter()
        inputTerminal.bTerminalID   = 3
        inputTerminal.wTerminalType = uac2.InputTerminalTypes.MICROPHONE
        inputTerminal.bCSourceID    = 1
        inputTerminal.bNrChannels   = 1
        audioControlInterface.add_subordinate_descriptor(inputTerminal)

        # AudioControl Interface Descriptor (OutputTerminal)
        outputTerminal               = uac2.OutputTerminalDescriptorEmitter()
        outputTerminal.bTerminalID   = 4
        outputTerminal.wTerminalType = uac2.OutputTerminalTypes.SPEAKER
        outputTerminal.bSourceID     = 3
        outputTerminal.bCSourceID    = 1
        audioControlInterface.add_subordinate_descriptor(outputTerminal)

        return audioControlInterface

    def create_output_channels_descriptor(self, c):
        #
        # Interface Descriptor (Streaming, OUT, quiet setting)
        #
        quietAudioStreamingInterface                  = uac2.AudioStreamingInterfaceDescriptorEmitter()
        quietAudioStreamingInterface.bInterfaceNumber = 1
        c.add_subordinate_descriptor(quietAudioStreamingInterface)

        # Interface Descriptor (Streaming, OUT, active setting)
        activeAudioStreamingInterface                   = uac2.AudioStreamingInterfaceDescriptorEmitter()
        activeAudioStreamingInterface.bInterfaceNumber  = 1
        activeAudioStreamingInterface.bAlternateSetting = 1
        activeAudioStreamingInterface.bNumEndpoints     = 2
        c.add_subordinate_descriptor(activeAudioStreamingInterface)

        # AudioStreaming Interface Descriptor (General)
        audioStreamingInterface               = uac2.ClassSpecificAudioStreamingInterfaceDescriptorEmitter()
        audioStreamingInterface.bTerminalLink = 4
        audioStreamingInterface.bFormatType   = uac2.FormatTypes.FORMAT_TYPE_I
        audioStreamingInterface.bmFormats     = uac2.TypeIFormats.PCM
        audioStreamingInterface.bNrChannels   = 2
        c.add_subordinate_descriptor(audioStreamingInterface)

        # AudioStreaming Interface Descriptor (Type I)
        typeIStreamingInterface  = uac2.TypeIFormatTypeDescriptorEmitter()
        typeIStreamingInterface.bSubslotSize   = 3  # 24 bit per sample
        typeIStreamingInterface.bBitResolution = 24 # we use all 24 bits
        c.add_subordinate_descriptor(typeIStreamingInterface)

        # Endpoint Descriptor (Audio out)
        audioOutEndpoint = standard.EndpointDescriptorEmitter()
        audioOutEndpoint.bEndpointAddress     = USBDirection.OUT.to_endpoint_address(1) # EP 1 OUT
        audioOutEndpoint.bmAttributes         = USBTransferType.ISOCHRONOUS  | \
                                                USBSynchronizationType.ASYNC | \
                                                USBUsageType.DATA
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
                                               USBSynchronizationType.NONE  | \
                                               USBUsageType.FEEDBACK
        feedbackInEndpoint.wMaxPacketSize    = 4
        feedbackInEndpoint.bInterval         = 4
        c.add_subordinate_descriptor(feedbackInEndpoint)

    def create_input_channels_descriptor(self, c):
        #
        # Interface Descriptor (Streaming, IN, quiet setting)
        #
        quietAudioStreamingInterface                  = uac2.AudioStreamingInterfaceDescriptorEmitter()
        quietAudioStreamingInterface.bInterfaceNumber = 2
        c.add_subordinate_descriptor(quietAudioStreamingInterface)

        # Interface Descriptor (Streaming, IN, active setting)
        activeAudioStreamingInterface                   = uac2.AudioStreamingInterfaceDescriptorEmitter()
        activeAudioStreamingInterface.bInterfaceNumber  = 2
        activeAudioStreamingInterface.bAlternateSetting = 1
        activeAudioStreamingInterface.bNumEndpoints     = 1
        c.add_subordinate_descriptor(activeAudioStreamingInterface)

        # AudioStreaming Interface Descriptor (General)
        audioStreamingInterface               = uac2.ClassSpecificAudioStreamingInterfaceDescriptorEmitter()
        audioStreamingInterface.bTerminalLink = 3
        audioStreamingInterface.bFormatType   = uac2.FormatTypes.FORMAT_TYPE_I
        audioStreamingInterface.bmFormats     = uac2.TypeIFormats.PCM
        audioStreamingInterface.bNrChannels   = 1
        c.add_subordinate_descriptor(audioStreamingInterface)

        # AudioStreaming Interface Descriptor (Type I)
        typeIStreamingInterface  = uac2.TypeIFormatTypeDescriptorEmitter()
        typeIStreamingInterface.bSubslotSize   = 3  # 24 bit per sample
        typeIStreamingInterface.bBitResolution = 24 # we use all 24 bits
        c.add_subordinate_descriptor(typeIStreamingInterface)

        # Endpoint Descriptor (Audio out)
        audioOutEndpoint = standard.EndpointDescriptorEmitter()
        audioOutEndpoint.bEndpointAddress     = USBDirection.IN.to_endpoint_address(2) # EP 2 IN
        audioOutEndpoint.bmAttributes         = USBTransferType.ISOCHRONOUS  | \
                                                USBSynchronizationType.ASYNC | \
                                                USBUsageType.DATA
        audioOutEndpoint.wMaxPacketSize = self.MAX_PACKET_SIZE
        audioOutEndpoint.bInterval       = 1
        c.add_subordinate_descriptor(audioOutEndpoint)

        # AudioControl Endpoint Descriptor
        audioControlEndpoint = uac2.ClassSpecificAudioStreamingIsochronousAudioDataEndpointDescriptorEmitter()
        c.add_subordinate_descriptor(audioControlEndpoint)

    def elaborate(self, platform):
        m = Module()

        # Generate our domain clocks/resets.
        m.submodules.car = platform.clock_domain_generator()

        # Create our USB-to-serial converter.
        ulpi = platform.request(platform.default_usb_connection)
        m.submodules.usb = usb = USBDevice(bus=ulpi)

        # Add our standard control endpoint to the device.
        descriptors = self.create_descriptors()
        control_ep = usb.add_standard_control_endpoint(descriptors)

        # Attach our class request handlers.
        control_ep.add_request_handler(UAC2RequestHandlers())

        # Attach class-request handlers that stall any vendor or reserved requests,
        # as we don't have or need any.
        stall_condition = lambda setup : \
            (setup.type == USBRequestType.VENDOR) | \
            (setup.type == USBRequestType.RESERVED)
        control_ep.add_request_handler(StallOnlyRequestHandler(stall_condition))

        ep1_out = USBIsochronousOutEndpoint(
            endpoint_number=1, # EP 1 OUT
            max_packet_size=self.MAX_PACKET_SIZE,
        )
        usb.add_endpoint(ep1_out)

        ep1_in = USBIsochronousInEndpoint(
            endpoint_number=1, # EP 1 IN
            max_packet_size=4
        )
        usb.add_endpoint(ep1_in)

        ep2_in = USBIsochronousInEndpoint(
            endpoint_number=2, # EP 2 IN
            max_packet_size=self.MAX_PACKET_SIZE
        )
        usb.add_endpoint(ep2_in)

        leds    = Cat(platform.request_optional("led", i, default=NullPin()) for i in range(8))
        with m.If(ep1_out.stream.valid):
            m.d.usb += [
                leds.eq(ep1_out.stream.payload),
            ]

        # Connect our device as a high speed device
        m.d.comb += [
            ep2_in.bytes_in_frame.eq(self.MAX_PACKET_SIZE * 3),
            ep2_in.value.eq(ep2_in.address),
            ep1_out.stream.ready .eq(1),
            usb.connect          .eq(1),
            usb.full_speed_only  .eq(0),
        ]

        return m

class UAC2RequestHandlers(USBRequestHandler):
    """ Minimal set of request handlers to implement UAC2 functionality. """

    def elaborate(self, platform):
        m = Module()

        interface         = self.interface
        setup             = self.interface.setup

        m.submodules.transmitter = transmitter = \
            StreamSerializer(data_length=14, domain="usb", stream_type=USBInStreamInterface, max_length_width=14)

        #
        # Class request handlers.
        #

        with m.If(setup.type == USBRequestType.CLASS):
            with m.Switch(setup.request):
                request_clock_freq = (setup.value == 0x100) & (setup.index == 0x0101)
                with m.Case(AudioClassSpecificRequestCodes.RANGE):
                    m.d.comb += transmitter.stream.attach(self.interface.tx)

                    with m.If(request_clock_freq & (setup.length == 2)):
                        m.d.comb += [
                            Cat(transmitter.data[0:1]).eq(Const(0x1, 16)),
                            transmitter.max_length.eq(2)
                        ]

                    with m.Elif(request_clock_freq & (setup.length == 14)):
                        m.d.comb += [
                            Cat(transmitter.data).eq(
                                Cat(Const(0x1, 16), # no triples
                                    Const(48000, 32), # MIN
                                    Const(48000, 32), # MAX
                                    Const(48000, 32))), # RES
                            transmitter.max_length.eq(14)
                        ]
                    with m.Else():
                        m.d.comb += interface.handshakes_out.stall.eq(1)

                    # ... trigger it to respond when data's requested...
                    with m.If(interface.data_requested):
                        m.d.comb += transmitter.start.eq(1)

                    # ... and ACK our status stage.
                    with m.If(interface.status_requested):
                        m.d.comb += interface.handshakes_out.ack.eq(1)

                with m.Case(AudioClassSpecificRequestCodes.CUR):
                    m.d.comb += transmitter.stream.attach(self.interface.tx)
                    with m.If(request_clock_freq & (setup.length == 4)):
                        m.d.comb += [
                            Cat(transmitter.data[0:4]).eq(Const(48000, 32)),
                            transmitter.max_length.eq(4)
                        ]
                    with m.Else():
                        m.d.comb += interface.handshakes_out.stall.eq(1)

                    # ... trigger it to respond when data's requested...
                    with m.If(interface.data_requested):
                        m.d.comb += transmitter.start.eq(1)

                    # ... and ACK our status stage.
                    with m.If(interface.status_requested):
                        m.d.comb += interface.handshakes_out.ack.eq(1)

                with m.Case(USBStandardRequests.SET_INTERFACE):
                    with m.If(interface.status_requested):
                        m.d.comb += [
                            interface.handshakes_out.stall.eq(0),
                            interface.handshakes_out.ack.eq(1)
                        ]

                with m.Case():
                    #
                    # Stall unhandled requests.
                    #
                    with m.If(interface.status_requested | interface.data_requested):
                        m.d.comb += interface.handshakes_out.stall.eq(1)

                return m

if __name__ == "__main__":
    os.environ["LUNA_PLATFORM"] = "qmtech_ep4ce15_platform:JT51SynthPlatform"
    e = USB2AudioInterface()
    d = e.create_descriptors()
    descriptor_bytes = d.get_descriptor_bytes(2)
    print(f"descriptor length: {len(descriptor_bytes)} bytes: {str(descriptor_bytes.hex())}")
    top_level_cli(USB2AudioInterface)