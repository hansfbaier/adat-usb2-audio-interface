from enum import IntEnum
from amaranth import *
from luna.gateware.usb.usb2.request   import USBRequestHandler
from luna.gateware.stream.generator   import StreamSerializer

from usb_protocol.types                       import USBRequestType, USBRequestRecipient, USBStandardRequests
from usb_protocol.types.descriptors.uac2      import AudioClassSpecificRequestCodes, ClockSourceControlSelectors, ClockSelectorControlSelectors
from luna.gateware.usb.stream                 import USBInStreamInterface

from usb_descriptors import USBDescriptors

class VendorRequests(IntEnum):
    ILA_STOP_CAPTURE = 0

class UAC2RequestHandlers(USBRequestHandler):
    """ request handlers to implement UAC2 functionality. """
    def __init__(self):
        super().__init__()

        self.output_interface_altsetting_nr = Signal(3)
        self.input_interface_altsetting_nr  = Signal(3)
        self.interface_settings_changed     = Signal()
        self.clock_select_out               = Signal(2)

    def elaborate(self, platform):
        m = Module()

        interface         = self.interface
        setup             = self.interface.setup

        clock_select = Signal.like(self.clock_select_out)
        m.d.comb    += self.clock_select_out.eq(clock_select)

        m.submodules.transmitter = transmitter = \
            StreamSerializer(data_length=14, domain="usb", stream_type=USBInStreamInterface, max_length_width=14)

        m.d.usb += self.interface_settings_changed.eq(0)

        data    = Array(Signal(8, name=f"data{i}") for i in range(4))
        datapos = Signal(2)

        #
        # Class request handlers.
        #
        with m.If(setup.type == USBRequestType.STANDARD):
            with m.If((setup.recipient == USBRequestRecipient.INTERFACE) &
                      (setup.request == USBStandardRequests.SET_INTERFACE)):

                interface_nr   = setup.index
                alt_setting_nr = setup.value

                m.d.usb += [
                    self.output_interface_altsetting_nr.eq(0),
                    self.input_interface_altsetting_nr.eq(0),
                    self.interface_settings_changed.eq(1),
                ]

                with m.Switch(interface_nr):
                    with m.Case(1):
                        m.d.usb += self.output_interface_altsetting_nr.eq(alt_setting_nr)
                    with m.Case(2):
                        m.d.usb += self.input_interface_altsetting_nr.eq(alt_setting_nr)

                # Always ACK the data out...
                with m.If(interface.rx_ready_for_response):
                    m.d.comb += interface.handshakes_out.ack.eq(1)

                # ... and accept whatever the request was.
                with m.If(interface.status_requested):
                    m.d.comb += self.send_zlp()

        clock_freq =   (setup.value == Const(ClockSourceControlSelectors.CS_SAM_FREQ_CONTROL << 8, 16)) \
                     & (setup.index == Const(USBDescriptors.CLOCK_ID << 8, 16))

        clock_selector =   (setup.value == Const(ClockSelectorControlSelectors.CX_CLOCK_SELECTOR_CONTROL << 8, 16)) \
                         & (setup.index == Const(USBDescriptors.CLOCK_SELECTOR_ID << 8, 16))

        request_clock_freq     = clock_freq     & setup.is_in_request
        set_clock_freq         = clock_freq     & ~setup.is_in_request
        request_clock_selector = clock_selector & setup.is_in_request
        set_clock_selector     = clock_selector & ~setup.is_in_request

        SRATE_44_1k = Const(44100, 32)
        SRATE_48k   = Const(48000, 32)
        ZERO        = Const(0, 32)

        with m.Elif(setup.type == USBRequestType.CLASS):
            with m.Switch(setup.request):
                with m.Case(AudioClassSpecificRequestCodes.RANGE):
                    m.d.comb += transmitter.stream.attach(self.interface.tx)

                    with m.If(request_clock_freq):
                        m.d.comb += [
                            Cat(transmitter.data).eq(
                                Cat(Const(0x2,   16),   # no triples
                                    SRATE_44_1k, # MIN
                                    SRATE_44_1k, # MAX
                                    ZERO,        # RES
                                    SRATE_48k,   # MIN
                                    SRATE_48k,   # MAX
                                    ZERO)),      # RES
                            transmitter.max_length.eq(setup.length)
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

                    with m.If(request_clock_selector & (setup.length == 1)):
                        # The clock selector only has one input, so
                        # there is no choice: always return 1
                        m.d.comb += transmitter.max_length.eq(1)
                        with m.Switch(clock_select):
                            m.d.comb += transmitter.data[0].eq(1)

                        # ... trigger it to respond when data's requested...
                        with m.If(interface.data_requested):
                            m.d.comb += transmitter.start.eq(1)

                        # ... and ACK our status stage.
                        with m.If(interface.status_requested):
                            m.d.comb += interface.handshakes_out.ack.eq(1)

                    with m.If(request_clock_freq & (setup.length == 4)):
                        m.d.comb += transmitter.max_length.eq(4)
                        with m.Switch(clock_select):
                            with m.Case(0):
                                m.d.comb += Cat(transmitter.data[0:4]).eq(SRATE_44_1k)
                            with m.Default():
                                m.d.comb += Cat(transmitter.data[0:4]).eq(SRATE_48k)

                        # ... trigger it to respond when data's requested...
                        with m.If(interface.data_requested):
                            m.d.comb += transmitter.start.eq(1)

                        # ... and ACK our status stage.
                        with m.If(interface.status_requested):
                            m.d.comb += interface.handshakes_out.ack.eq(1)

                    with m.If(set_clock_selector & (setup.length == 1)):
                        # There is only one input for the clock selector
                        # so no choice here. Simply do nothing

                        # Once the receive is complete, respond with an ACK.
                        with m.If(interface.rx_ready_for_response):
                            m.d.comb += interface.handshakes_out.ack.eq(1)

                        # If we reach the status stage, send a ZLP.
                        with m.If(interface.status_requested):
                            m.d.comb += self.send_zlp()


                    with m.Elif(set_clock_freq & (setup.length == 4)):
                        with m.If(interface.rx.valid & interface.rx.next):
                            m.d.usb += [
                                data[datapos].eq(interface.rx.payload),
                                datapos.eq(datapos + 1),
                            ]

                        # Once the receive is complete, respond with an ACK.
                        with m.If(interface.rx_ready_for_response):
                            m.d.comb += interface.handshakes_out.ack.eq(1)

                        # If we reach the status stage, send a ZLP.
                        with m.If(interface.status_requested):
                            m.d.comb += self.send_zlp()

                            # and select the requested clock
                            with m.If(datapos == 0):
                                with m.If(Cat(data) == SRATE_44_1k):
                                    m.d.usb += clock_select.eq(0)
                                with m.Else():
                                    m.d.usb += clock_select.eq(1)

                    with m.Else():
                        m.d.comb += interface.handshakes_out.stall.eq(1)

                with m.Default():
                    #
                    # Stall unhandled requests.
                    #
                    with m.If(interface.status_requested | interface.data_requested):
                        m.d.comb += interface.handshakes_out.stall.eq(1)

        with m.Elif(setup.type == USBRequestType.VENDOR):
            with m.Switch(setup.request):
                with m.Case(VendorRequests.ILA_STOP_CAPTURE):
                    # TODO - will be implemented when needed
                    pass

                with m.Default():
                    m.d.comb += self.interface.handshakes_out.stall.eq(1)

        with m.Else():
            m.d.comb += self.interface.handshakes_out.stall.eq(1)

        return m
