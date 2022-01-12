#!/usr/bin/env python3
#
# Copyright (c) 2021 Hans Baier <hansfbaier@gmail.com>
# SPDX-License-Identifier: CERN-OHL-W-2.0
import os

from amaranth            import *
from amaranth.lib.fifo   import AsyncFIFOBuffered, AsyncFIFO, SyncFIFOBuffered, SyncFIFO
from amaranth.lib.cdc    import FFSynchronizer

from amlib.stream        import connect_fifo_to_stream, connect_stream_to_fifo
from amlib.io.i2s        import I2STransmitter

from luna                import top_level_cli
from luna.usb2           import USBDevice, \
                                USBStreamInEndpoint, \
                                USBStreamOutEndpoint, \
                                USBIsochronousInMemoryEndpoint, \
                                USBIsochronousOutStreamEndpoint, \
                                USBIsochronousInStreamEndpoint

from usb_protocol.types                       import USBRequestType, USBStandardRequests

from luna.gateware.usb.usb2.device            import USBDevice

from adat import ADATTransmitter, ADATReceiver
from adat import EdgeToPulse

from usb_stream_to_channels  import USBStreamToChannels
from channels_to_usb_stream  import ChannelsToUSBStream
from channel_stream_combiner import ChannelStreamCombiner
from channel_stream_splitter import ChannelStreamSplitter
from bundle_multiplexer      import BundleMultiplexer
from bundle_demultiplexer    import BundleDemultiplexer
from stereopair_extractor    import StereoPairExtractor
from requesthandlers         import UAC2RequestHandlers
from debug                   import setup_ila, add_debug_led_array

from usb_descriptors import USBDescriptors

class USB2AudioInterface(Elaboratable):
    """ USB Audio Class v2 interface """
    # one isochronous packet typically has 6 or 7 samples of 8 channels of 32 bit samples
    # 6 samples * 8 channels * 4 bytes/sample = 192 bytes
    # 7 samples * 8 channels * 4 bytes/sample = 224 bytes
    USB2_NO_CHANNELS     = 4
    USB1_NO_CHANNELS     = 32 + USB2_NO_CHANNELS
    USB2_MAX_PACKET_SIZE = int(224 // 8 * USB2_NO_CHANNELS)
    USB1_MAX_PACKET_SIZE = int(224 * 4 + USB2_MAX_PACKET_SIZE)
    INPUT_CDC_FIFO_DEPTH = 256 * 4

    USE_ILA             = False
    ILA_MAX_PACKET_SIZE = 512

    USE_DEBUG_LED_ARRAY = True

    def elaborate(self, platform):
        m = Module()

        usb1_number_of_channels      = self.USB1_NO_CHANNELS
        usb1_number_of_channels_bits = Shape.cast(range(usb1_number_of_channels)).width
        usb2_number_of_channels      = self.USB2_NO_CHANNELS
        usb2_number_of_channels_bits = Shape.cast(range(usb2_number_of_channels)).width
        audio_bits                   = 24
        adat_number_of_channels      = usb1_number_of_channels - usb2_number_of_channels

        m.submodules.car = platform.clock_domain_generator()

        #
        # USB
        #
        ulpi1 = platform.request("ulpi", 1)
        ulpi2 = platform.request("ulpi", 2)
        m.submodules.usb1 = usb1 = USBDevice(bus=ulpi1)
        m.submodules.usb2 = usb2 = USBDevice(bus=ulpi2)

        descriptors = USBDescriptors(ila_max_packet_size=self.ILA_MAX_PACKET_SIZE, \
                                     use_ila=self.USE_ILA)

        usb1_control_ep = usb1.add_control_endpoint()
        usb1_descriptors = descriptors.create_usb1_descriptors(usb1_number_of_channels, self.USB1_MAX_PACKET_SIZE)
        usb1_control_ep.add_standard_request_handlers(usb1_descriptors, blacklist=[
            lambda setup:   (setup.type    == USBRequestType.STANDARD)
                          & (setup.request == USBStandardRequests.SET_INTERFACE)
        ])
        usb1_class_request_handler = UAC2RequestHandlers()
        usb1_control_ep.add_request_handler(usb1_class_request_handler)

        usb2_control_ep = usb2.add_control_endpoint()
        usb2_descriptors = descriptors.create_usb2_descriptors(usb2_number_of_channels, self.USB2_MAX_PACKET_SIZE)
        usb2_control_ep.add_standard_request_handlers(usb2_descriptors, blacklist=[
            lambda setup:   (setup.type    == USBRequestType.STANDARD)
                          & (setup.request == USBStandardRequests.SET_INTERFACE)
        ])
        usb2_class_request_handler = UAC2RequestHandlers()
        usb2_control_ep.add_request_handler(usb2_class_request_handler)

        # audio out ports of the host
        usb1_ep1_out = USBIsochronousOutStreamEndpoint(
            endpoint_number=1, # EP 1 OUT
            max_packet_size=self.USB1_MAX_PACKET_SIZE)
        usb1.add_endpoint(usb1_ep1_out)
        usb2_ep1_out = USBIsochronousOutStreamEndpoint(
            endpoint_number=1, # EP 1 OUT
            max_packet_size=self.USB2_MAX_PACKET_SIZE)
        usb2.add_endpoint(usb2_ep1_out)

        # audio rate feedback input ports of the host
        usb1_ep1_in = USBIsochronousInMemoryEndpoint(
            endpoint_number=1, # EP 1 IN
            max_packet_size=4)
        usb1.add_endpoint(usb1_ep1_in)
        usb2_ep1_in = USBIsochronousInMemoryEndpoint(
            endpoint_number=1, # EP 1 IN
            max_packet_size=4)
        usb2.add_endpoint(usb2_ep1_in)

        # audio input ports of the host
        usb1_ep2_in = USBIsochronousInStreamEndpoint(
            endpoint_number=2, # EP 2 IN
            max_packet_size=self.USB1_MAX_PACKET_SIZE)
        usb1.add_endpoint(usb1_ep2_in)
        usb2_ep2_in = USBIsochronousInStreamEndpoint(
            endpoint_number=2, # EP 2 IN
            max_packet_size=self.USB2_MAX_PACKET_SIZE)
        usb2.add_endpoint(usb2_ep2_in)

        # MIDI endpoints
        usb1_ep3_out = USBStreamOutEndpoint(
            endpoint_number=3, # EP 3 OUT
            max_packet_size=USBDescriptors.MAX_PACKET_SIZE_MIDI)
        usb1.add_endpoint(usb1_ep3_out)
        usb2_ep3_out = USBStreamOutEndpoint(
            endpoint_number=3, # EP 3 OUT
            max_packet_size=USBDescriptors.MAX_PACKET_SIZE_MIDI)
        usb2.add_endpoint(usb2_ep3_out)

        usb1_ep3_in = USBStreamInEndpoint(
            endpoint_number=3, # EP 3 IN
            max_packet_size=USBDescriptors.MAX_PACKET_SIZE_MIDI)
        usb1.add_endpoint(usb1_ep3_in)
        usb2_ep3_in = USBStreamInEndpoint(
            endpoint_number=3, # EP 3 IN
            max_packet_size=USBDescriptors.MAX_PACKET_SIZE_MIDI)
        usb2.add_endpoint(usb2_ep3_in)


        m.d.comb += [
            usb1.connect          .eq(1),
            usb2.connect          .eq(1),
            # Connect our device as a high speed device
            usb1.full_speed_only  .eq(0),
            usb2.full_speed_only  .eq(0),
        ]

        usb1_audio_in_frame_bytes = \
            self.calculate_usb_input_frame_size(m, "usb1", usb1_ep1_out, usb1_ep2_in, usb1_number_of_channels, self.USB1_MAX_PACKET_SIZE)
        usb2_audio_in_frame_bytes = \
            self.calculate_usb_input_frame_size(m, "usb2", usb2_ep1_out, usb2_ep2_in, usb2_number_of_channels, self.USB2_MAX_PACKET_SIZE)

        usb1_sof_counter, usb1_to_output_fifo_level, usb1_to_output_fifo_depth, \
        usb2_sof_counter, usb2_to_usb1_fifo_level, usb2_to_usb1_fifo_depth = \
            self.create_sample_rate_feedback_circuit(m, usb1, usb1_ep1_in, usb2, usb2_ep1_in)

        usb1_audio_in_active  = self.detect_active_audio_in (m, "usb1", usb1, usb1_ep2_in)
        usb2_audio_in_active  = self.detect_active_audio_in (m, "usb2", usb2, usb2_ep2_in)
        usb2_audio_out_active = self.detect_active_audio_out(m, "usb2", usb2, usb2_ep1_out)

        #
        # USB <-> Channel Stream conversion
        #
        m.submodules.usb1_to_channel_stream = usb1_to_channel_stream = \
            DomainRenamer("usb")(USBStreamToChannels(usb1_number_of_channels))
        m.submodules.usb2_to_channel_stream = usb2_to_channel_stream = \
            DomainRenamer("usb")(USBStreamToChannels(usb2_number_of_channels))

        m.submodules.usb1_channel_stream_combiner = usb1_channel_stream_combiner = \
            DomainRenamer("usb")(ChannelStreamCombiner(adat_number_of_channels, usb2_number_of_channels))

        m.submodules.usb1_channel_stream_splitter = usb1_channel_stream_splitter = \
            DomainRenamer("usb")(ChannelStreamSplitter(adat_number_of_channels, usb2_number_of_channels))

        m.submodules.channels_to_usb1_stream = channels_to_usb1_stream = \
            DomainRenamer("usb")(ChannelsToUSBStream(usb1_number_of_channels, max_packet_size=self.USB1_MAX_PACKET_SIZE))
        m.submodules.channels_to_usb2_stream = channels_to_usb2_stream = \
            DomainRenamer("usb")(ChannelsToUSBStream(usb2_number_of_channels, max_packet_size=self.USB2_MAX_PACKET_SIZE))

        usb1_no_channels      = Signal(range(usb1_number_of_channels * 2), reset=2)
        usb1_no_channels_sync = Signal.like(usb1_no_channels)

        usb2_no_channels      = Signal(range(usb2_number_of_channels * 2), reset=2)

        m.submodules.no_channels_sync_synchronizer = FFSynchronizer(usb1_no_channels, usb1_no_channels_sync, o_domain="sync")

        m.d.comb += [
            usb1_to_channel_stream.no_channels_in.eq(usb1_no_channels),
            channels_to_usb1_stream.no_channels_in.eq(usb1_no_channels),
            channels_to_usb1_stream.audio_in_active.eq(usb1_audio_in_active),

            usb2_to_channel_stream.no_channels_in.eq(usb2_no_channels),
            channels_to_usb2_stream.no_channels_in.eq(usb2_no_channels),
            channels_to_usb2_stream.audio_in_active.eq(usb2_audio_in_active),
        ]

        with m.Switch(usb1_class_request_handler.output_interface_altsetting_nr):
            with m.Case(2):
                m.d.usb += usb1_no_channels.eq(usb1_number_of_channels)
            with m.Default():
                m.d.usb += usb1_no_channels.eq(2)

        with m.Switch(usb2_class_request_handler.output_interface_altsetting_nr):
            with m.Case(2):
                m.d.usb += usb2_no_channels.eq(usb2_number_of_channels)
            with m.Default():
                m.d.usb += usb2_no_channels.eq(2)

        m.submodules.usb_to_output_fifo = usb1_to_output_fifo = \
            AsyncFIFO(width=audio_bits + usb1_number_of_channels_bits + 2, depth=usb1_to_output_fifo_depth, w_domain="usb", r_domain="sync")

        m.submodules.usb2_to_usb1_fifo = usb2_to_usb1_fifo = \
            DomainRenamer("usb")(SyncFIFOBuffered(width=audio_bits + usb2_number_of_channels_bits + 2, depth=usb2_to_usb1_fifo_depth))

        m.submodules.bundle_demultiplexer = bundle_demultiplexer = BundleDemultiplexer()
        m.submodules.bundle_multiplexer   = bundle_multiplexer   = DomainRenamer("fast")(BundleMultiplexer())

        adat_transmitters = []
        adat_receivers    = []
        adat_pads         = []
        for i in range(1, 5):
            transmitter = ADATTransmitter(fifo_depth=9*4)
            setattr(m.submodules, f"adat{i}_transmitter", transmitter)
            adat_transmitters.append(transmitter)

            receiver = DomainRenamer("fast")(ADATReceiver(platform.fast_domain_clock_freq))
            setattr(m.submodules, f"adat{i}_receiver", receiver)
            adat_receivers.append(receiver)

            adat_pads.append(platform.request("toslink", i))

        #
        # signal path: USB ===> ADAT transmitters
        #
        audio_bits_end         = audio_bits
        channel_bits_start     = audio_bits

        usb1_channel_bits_end  = channel_bits_start + usb1_number_of_channels_bits
        usb1_first_bit_pos     = usb1_channel_bits_end
        usb1_last_bit_pos      = usb1_first_bit_pos + 1

        m.d.comb += [
            # convert USB stream to channel splitter to (output audio, USB2 audio IN)
            usb1_to_channel_stream.usb_stream_in.stream_eq(usb1_ep1_out.stream),
            usb1_channel_stream_splitter.combined_channel_stream_in.stream_eq(usb1_to_channel_stream.channel_stream_out),

            *connect_stream_to_fifo(usb1_channel_stream_splitter.lower_channel_stream_out, usb1_to_output_fifo),

            usb1_to_output_fifo.w_data[channel_bits_start:usb1_channel_bits_end]
                .eq(usb1_channel_stream_splitter.lower_channel_stream_out.channel_nr),

            usb1_to_output_fifo.w_data[usb1_first_bit_pos]
                .eq(usb1_channel_stream_splitter.lower_channel_stream_out.first),

            usb1_to_output_fifo.w_data[usb1_last_bit_pos]
                .eq(usb1_channel_stream_splitter.lower_channel_stream_out.last),

            usb1_to_output_fifo.r_en  .eq(bundle_demultiplexer.channel_stream_in.ready),
            usb1_to_output_fifo_level .eq(usb1_to_output_fifo.w_level),

            # demultiplex channel stream to the different transmitters
            bundle_demultiplexer.channel_stream_in.payload.eq(usb1_to_output_fifo.r_data[0:audio_bits_end]),
            bundle_demultiplexer.channel_stream_in.channel_nr.eq(usb1_to_output_fifo.r_data[channel_bits_start:usb1_channel_bits_end]),
            bundle_demultiplexer.channel_stream_in.last.eq(usb1_to_output_fifo.r_data[-1]),
            bundle_demultiplexer.channel_stream_in.valid.eq(usb1_to_output_fifo.r_rdy & usb1_to_output_fifo.r_en),
            bundle_demultiplexer.no_channels_in.eq(usb1_no_channels_sync),
        ]

        # wire up transmitters / receivers
        for i in range(4):
            m.d.comb += [
                # transmitters
                adat_transmitters[i].sample_in           .eq(bundle_demultiplexer.bundles_out[i].payload),
                adat_transmitters[i].addr_in             .eq(bundle_demultiplexer.bundles_out[i].channel_nr),
                adat_transmitters[i].last_in             .eq(bundle_demultiplexer.bundles_out[i].last),
                adat_transmitters[i].valid_in            .eq(bundle_demultiplexer.bundles_out[i].valid),
                bundle_demultiplexer.bundles_out[i].ready.eq(adat_transmitters[i].ready_out),
                adat_transmitters[i].user_data_in .eq(0),

                adat_pads[i].tx.eq(adat_transmitters[i].adat_out),

                # receivers
                adat_receivers[i].adat_in.eq(adat_pads[i].rx),

                # wire up receive FIFO to ADAT receiver
                bundle_multiplexer.no_channels_in[i]        .eq(8),
                bundle_multiplexer.bundles_in[i].payload    .eq(adat_receivers[i].sample_out),
                bundle_multiplexer.bundles_in[i].channel_nr .eq(adat_receivers[i].addr_out),
                bundle_multiplexer.bundles_in[i].valid      .eq(adat_receivers[i].output_enable),
                bundle_multiplexer.bundles_in[i].last       .eq(adat_receivers[i].addr_out == 7),
                bundle_multiplexer.bundle_active_in[i]      .eq(adat_receivers[i].synced_out),
            ]

        #
        # signal path: ADAT receivers ===> USB
        #
        m.submodules.input_to_usb_fifo = input_to_usb_fifo = \
            AsyncFIFOBuffered(width=audio_bits + usb1_number_of_channels_bits + 2, depth=self.INPUT_CDC_FIFO_DEPTH, w_domain="fast", r_domain="usb")

        chnr_start        = audio_bits
        input_chnr_end    = chnr_start + adat_number_of_channels
        input_channel_nr  = input_to_usb_fifo.r_data[chnr_start:input_chnr_end]

        first_channel      = 0
        input_last_channel = (adat_number_of_channels - 1)

        m.d.comb += [
            # wire up receive FIFO to bundle multiplexer
            input_to_usb_fifo.w_data[0:chnr_start]        .eq(bundle_multiplexer.channel_stream_out.payload),
            input_to_usb_fifo.w_data[chnr_start:input_chnr_end] .eq(bundle_multiplexer.channel_stream_out.channel_nr),
            input_to_usb_fifo.w_en                        .eq(bundle_multiplexer.channel_stream_out.valid & input_to_usb_fifo.w_rdy),
            bundle_multiplexer.channel_stream_out.ready.eq(input_to_usb_fifo.w_rdy),

            # convert audio stream to USB stream
            # connect ADAT channels to combiner
            usb1_channel_stream_combiner.lower_channel_stream_in.payload    .eq(input_to_usb_fifo.r_data[0:chnr_start]),
            usb1_channel_stream_combiner.lower_channel_stream_in.channel_nr .eq(input_channel_nr),
            usb1_channel_stream_combiner.lower_channel_stream_in.first      .eq(input_channel_nr == first_channel),
            usb1_channel_stream_combiner.lower_channel_stream_in.last       .eq(input_channel_nr == input_last_channel),
            usb1_channel_stream_combiner.lower_channel_stream_in.valid      .eq(input_to_usb_fifo.r_rdy),
            input_to_usb_fifo.r_en.eq(usb1_channel_stream_combiner.lower_channel_stream_in.ready),

            # connect combiner output to USB1
            channels_to_usb1_stream.channel_stream_in.stream_eq(usb1_channel_stream_combiner.combined_channel_stream_out),
            channels_to_usb1_stream.data_requested_in .eq(usb1_ep2_in.data_requested),
            channels_to_usb1_stream.frame_finished_in .eq(usb1_ep2_in.frame_finished),

            # wire up USB1 audio IN
            usb1_ep2_in.stream.stream_eq(channels_to_usb1_stream.usb_stream_out),
        ]

        #
        # signal path: USB2 <-> USB1
        #
        usb2_channel_bits_end  = channel_bits_start + usb2_number_of_channels_bits
        usb2_first_bit_pos     = usb2_channel_bits_end
        usb2_last_bit_pos      = usb2_first_bit_pos + 1

        usb2_channel_nr        = usb2_to_usb1_fifo.r_data[chnr_start:usb2_channel_bits_end]
        m.d.comb +=[
            usb2_to_channel_stream.usb_stream_in.stream_eq(usb2_ep1_out.stream),
            *connect_stream_to_fifo(usb2_to_channel_stream.channel_stream_out, usb2_to_usb1_fifo),

            usb2_to_usb1_fifo.w_data[channel_bits_start:usb2_channel_bits_end]
                .eq(usb2_to_channel_stream.channel_stream_out.channel_nr),

            usb2_to_usb1_fifo.w_data[usb2_first_bit_pos]
                .eq(usb2_to_channel_stream.channel_stream_out.first),

            usb2_to_usb1_fifo.w_data[usb2_last_bit_pos]
                .eq(usb2_to_channel_stream.channel_stream_out.last),

            usb2_to_usb1_fifo_level
                .eq(usb2_to_usb1_fifo.w_level),

            # connect USB2 OUT channels to USB1 IN
            usb1_channel_stream_combiner.upper_channels_active_in           .eq(~usb2.suspended & usb2_audio_out_active),
            usb1_channel_stream_combiner.upper_channel_stream_in.payload    .eq(usb2_to_usb1_fifo.r_data[0:chnr_start]),
            usb1_channel_stream_combiner.upper_channel_stream_in.channel_nr .eq(usb2_channel_nr),
            usb1_channel_stream_combiner.upper_channel_stream_in.first      .eq(usb2_to_usb1_fifo.r_data[usb2_first_bit_pos]),
            usb1_channel_stream_combiner.upper_channel_stream_in.last       .eq(usb2_to_usb1_fifo.r_data[usb2_last_bit_pos]),
            usb1_channel_stream_combiner.upper_channel_stream_in.valid      .eq(usb2_to_usb1_fifo.r_rdy),
            usb2_to_usb1_fifo.r_en.eq(usb1_channel_stream_combiner.upper_channel_stream_in.ready),

            # connect USB2 IN channels to USB1 OUT
            channels_to_usb2_stream.channel_stream_in.stream_eq(usb1_channel_stream_splitter.upper_channel_stream_out),
            channels_to_usb2_stream.data_requested_in .eq(usb2_ep2_in.data_requested),
            channels_to_usb2_stream.frame_finished_in .eq(usb2_ep2_in.frame_finished),

            usb2_ep2_in.stream.stream_eq(channels_to_usb2_stream.usb_stream_out),
        ]

        #
        # I2S DACs
        #
        m.submodules.dac1_transmitter = dac1 = DomainRenamer("usb")(I2STransmitter(sample_width=audio_bits))
        m.submodules.dac2_transmitter = dac2 = DomainRenamer("usb")(I2STransmitter(sample_width=audio_bits))
        m.submodules.dac1_extractor   = dac1_extractor = DomainRenamer("usb")(StereoPairExtractor(usb1_number_of_channels))
        m.submodules.dac2_extractor   = dac2_extractor = DomainRenamer("usb")(StereoPairExtractor(usb1_number_of_channels))
        dac1_pads = platform.request("i2s", 1)
        dac2_pads = platform.request("i2s", 2)

        # divide bitclock to get word clock
        # each half cycle has 32 bits in it
        lrclk       = Signal(reset=1)
        bit_counter = Signal(6)

        m.d.dac   += bit_counter.eq(bit_counter + 1)
        m.d.comb  += lrclk.eq(bit_counter[-1])

        # hardwire DAC1 to channels 0/1 and DAC2 to 2/3
        # until making it switchable via USB request
        m.d.comb += [
            dac1_extractor.selected_channel_in.eq(0),
            # if stereo mode is enabled we want the second DAC to be wired
            # to main lef/right channels, just as the first one
            dac2_extractor.selected_channel_in.eq(Mux(usb1_no_channels == 2, 0, 2)),
        ]

        self.wire_up_dac(m, usb1_to_channel_stream, dac1_extractor, dac1, lrclk, dac1_pads)
        self.wire_up_dac(m, usb1_to_channel_stream, dac2_extractor, dac2, lrclk, dac2_pads)

        #
        # USB => output FIFO level debug signals
        #
        min_fifo_level = Signal.like(usb1_to_output_fifo_level, reset=usb1_to_output_fifo_depth)
        max_fifo_level = Signal.like(usb1_to_output_fifo_level)

        with m.If(usb1_to_output_fifo_level > max_fifo_level):
            m.d.sync += max_fifo_level.eq(usb1_to_output_fifo_level)

        with m.If(usb1_to_output_fifo_level < min_fifo_level):
            m.d.sync += min_fifo_level.eq(usb1_to_output_fifo_level)

        #
        # USB MIDI
        #
        usb_midi_fifo_depth = USBDescriptors.MAX_PACKET_SIZE_MIDI
        m.submodules.usb1_to_usb2_midi_fifo = usb1_to_usb2_midi_fifo = \
            DomainRenamer("usb")(SyncFIFOBuffered(width=8+2, depth=usb_midi_fifo_depth))
        m.submodules.usb2_to_usb1_midi_fifo = usb2_to_usb1_midi_fifo = \
            DomainRenamer("usb")(SyncFIFOBuffered(width=8+2, depth=usb_midi_fifo_depth))

        m.d.comb += [
            *connect_stream_to_fifo(usb1_ep3_out.stream,    usb1_to_usb2_midi_fifo, firstBit=-2, lastBit=-1),
            *connect_fifo_to_stream(usb1_to_usb2_midi_fifo, usb2_ep3_in.stream,     firstBit=-2, lastBit=-1),
            *connect_stream_to_fifo(usb2_ep3_out.stream,    usb2_to_usb1_midi_fifo, firstBit=-2, lastBit=-1),
            *connect_fifo_to_stream(usb2_to_usb1_midi_fifo, usb1_ep3_in.stream,     firstBit=-2, lastBit=-1),
        ]

        # Internal Logic Analyzer
        if self.USE_ILA:
            setup_ila(locals(), self.ILA_MAX_PACKET_SIZE)

        if self.USE_DEBUG_LED_ARRAY:
            add_debug_led_array(locals())

        usb_aux1 = platform.request("usb_aux", 1)
        usb_aux2 = platform.request("usb_aux", 2)

        #
        # board status LEDs
        #
        leds = platform.request("leds")
        m.d.comb += [
            leds.active1.eq(usb1.tx_activity_led | usb1.rx_activity_led),
            leds.suspended1.eq(usb1.suspended),
            leds.active2.eq(usb2.tx_activity_led | usb2.rx_activity_led),
            leds.suspended2.eq(usb2.suspended),
            leds.usb1.eq(usb_aux1.vbus),
            leds.usb2.eq(usb_aux2.vbus),
        ]
        m.d.comb += [getattr(leds, f"sync{i + 1}").eq(adat_receivers[i].synced_out) for i in range(4)]

        return m


    def detect_active_audio_in(self, m, name: str, usb, ep2_in):
        audio_in_seen   = Signal(name=f"{name}_audio_in_seen")
        audio_in_active = Signal(name=f"{name}_audio_in_active")

        # detect if we don't have a USB audio IN packet
        with m.If(usb.sof_detected):
            m.d.usb += [
                audio_in_active.eq(audio_in_seen),
                audio_in_seen.eq(0),
            ]

        with m.If(ep2_in.data_requested):
            m.d.usb += audio_in_seen.eq(1)

        return audio_in_active


    def detect_active_audio_out(self, m, name: str, usb, ep1_out):
        audio_out_seen   = Signal(name=f"{name}_audio_out_seen")
        audio_out_active = Signal(name=f"{name}_audio_out_active")

        # detect if we don't have a USB audio OUT packet
        with m.If(usb.sof_detected):
            m.d.usb += [
                audio_out_active.eq(audio_out_seen),
                audio_out_seen.eq(0),
            ]

        with m.If(ep1_out.stream.last):
            m.d.usb += audio_out_seen.eq(1)

        return audio_out_active


    def calculate_usb_input_frame_size(self, m: Module, usb_name: str, ep1_out, ep2_in, number_of_channels: int, max_packet_size: int):
        """calculate the number of bytes one packet of audio input contains"""

        audio_in_frame_byte_counter   = Signal(range(max_packet_size), name=f"{usb_name}_audio_in_frame_byte_counter", reset=24 * number_of_channels)
        audio_in_frame_bytes_counting = Signal(name=f"{usb_name}_audio_in_frame_bytes_counting")

        with m.If(ep1_out.stream.valid & ep1_out.stream.ready):
            with m.If(audio_in_frame_bytes_counting):
                m.d.usb += audio_in_frame_byte_counter.eq(audio_in_frame_byte_counter + 1)

            with m.If(ep1_out.stream.first):
                m.d.usb += [
                    audio_in_frame_byte_counter.eq(1),
                    audio_in_frame_bytes_counting.eq(1),
                ]
            with m.Elif(ep1_out.stream.last):
                m.d.usb += audio_in_frame_bytes_counting.eq(0)

        audio_in_frame_bytes = Signal.like(audio_in_frame_byte_counter, name=f"{usb_name}_audio_in_frame_bytes")
        with m.If(ep1_out.stream.last):
            m.d.usb += audio_in_frame_bytes.eq(audio_in_frame_byte_counter + 1)

        m.d.comb += ep2_in.bytes_in_frame.eq(audio_in_frame_bytes),

        return audio_in_frame_bytes


    def create_sample_rate_feedback_circuit(self, m: Module, usb1, usb1_ep1_in, usb2, usb2_ep1_in):
        #
        # USB rate feedback
        #
        adat_clock_usb = Signal()
        m.submodules.adat_clock_usb_sync  = FFSynchronizer(ClockSignal("adat"), adat_clock_usb, o_domain="usb")
        m.submodules.adat_clock_usb_pulse = adat_clock_usb_pulse = DomainRenamer("usb")(EdgeToPulse())
        adat_clock_tick = Signal()
        m.d.usb += [
            adat_clock_usb_pulse.edge_in.eq(adat_clock_usb),
            adat_clock_tick.eq(adat_clock_usb_pulse.pulse_out),
        ]

        usb1_feedback_value     = Signal(32, reset=0x60000)
        usb1_bit_pos            = Signal(5)
        usb2_feedback_value     = Signal(32, reset=0x60000)
        usb2_bit_pos            = Signal(5)

        # this tracks the number of ADAT frames in N microframes
        # with 12.288MHz / 8kHz = 1536 samples per microframe
        # we have N = 256, so we need
        # math.ceil(math.log2(1536 * 256)) = 19 bits
        usb1_adat_clock_counter      = Signal(19)
        usb2_adat_clock_counter      = Signal(19)

        # according to USB2 standard chapter 5.12.4.2
        # we need at least 2**13 / 2**8 = 2**5 = 32 SOF-frames of
        # sample master frequency counter to get the minimal
        # precision for the sample frequency estimate
        # / 2**8 because the ADAT-clock = 256 times = 2**8
        # the sample frequency
        # we average over 256 microframes, because that gives
        # us the maximum precision needed by the feedback endpoint
        usb1_sof_counter        = Signal(8)
        usb2_sof_counter        = Signal(8)

        # since samples are constantly consumed from the FIFO
        # half the maximum USB packet size should be more than enough
        usb1_to_output_fifo_depth = self.USB1_MAX_PACKET_SIZE // 2
        usb1_to_output_fifo_level = Signal(range(usb1_to_output_fifo_depth + 1))
        print("usb1_to_output_fifo_depth in bits: " + str(usb1_to_output_fifo_level.width))
        usb1_fifo_level_feedback  = Signal.like(usb1_to_output_fifo_level)
        m.d.comb += usb1_fifo_level_feedback.eq(usb1_to_output_fifo_level >> (usb1_to_output_fifo_level.width - 7))

        usb2_to_usb1_fifo_depth = self.USB2_MAX_PACKET_SIZE // 2
        usb2_to_usb1_fifo_level = Signal(range(usb2_to_usb1_fifo_depth + 1))
        print("usb2_to_usb1_fifo_depth in bits: " + str(usb2_to_usb1_fifo_level.width))
        usb2_fifo_level_feedback  = Signal.like(usb2_to_usb1_fifo_level)
        m.d.comb += usb2_fifo_level_feedback.eq(usb2_to_usb1_fifo_level >> (usb2_to_usb1_fifo_level.width - 4))

        with m.If(adat_clock_tick):
            m.d.usb += [
                usb1_adat_clock_counter.eq(usb1_adat_clock_counter + 1),
                usb2_adat_clock_counter.eq(usb2_adat_clock_counter + 1),
            ]

        with m.If(usb1.sof_detected):
            m.d.usb += usb1_sof_counter.eq(usb1_sof_counter + 1)

            with m.If(usb1_sof_counter == 0):
                # when feedbackValue == adat_clock_counter the
                # FIFO underflows slowly, but also when
                # feedbackValue == adat_clock_counter + 1
                # the FIFO slowly but surely fills to overflow.
                # since both of those feedback values are only one apart,
                # we need to start with the slowly overflowing value and
                # provide negative feedback proportional to the fill level
                # of the FIFO
                m.d.usb += [
                    usb1_feedback_value.eq(usb1_adat_clock_counter + 1 - usb1_fifo_level_feedback),
                    usb1_adat_clock_counter.eq(0),
                ]

        with m.If(usb2.sof_detected):
            m.d.usb += usb2_sof_counter.eq(usb2_sof_counter + 1)

            with m.If(usb2_sof_counter == 0):
                m.d.usb += [
                    usb2_feedback_value.eq(usb2_adat_clock_counter + 1 - usb2_fifo_level_feedback),
                    usb2_adat_clock_counter.eq(0),
                ]


        m.d.comb += [
            usb1_ep1_in.bytes_in_frame.eq(4),
            usb1_bit_pos.eq(usb1_ep1_in.address << 3),
            usb1_ep1_in.value.eq(0xff & (usb1_feedback_value >> usb1_bit_pos)),

            usb2_ep1_in.bytes_in_frame.eq(4),
            usb2_bit_pos.eq(usb2_ep1_in.address << 3),
            usb2_ep1_in.value.eq(0xff & (usb2_feedback_value >> usb2_bit_pos)),
        ]

        return (usb1_sof_counter, usb1_to_output_fifo_level, usb1_to_output_fifo_depth, \
                usb2_sof_counter, usb2_to_usb1_fifo_level, usb2_to_usb1_fifo_depth)


    def wire_up_dac(self, m, usb_to_channel_stream, dac_extractor, dac, lrclk, dac_pads):
        # wire up DAC extractor
        m.d.comb += [
            dac_extractor.channel_stream_in.valid.eq(  usb_to_channel_stream.channel_stream_out.valid
                                                      & usb_to_channel_stream.channel_stream_out.ready),
            dac_extractor.channel_stream_in.payload.eq(usb_to_channel_stream.channel_stream_out.payload),
            dac_extractor.channel_stream_in.channel_nr.eq(usb_to_channel_stream.channel_stream_out.channel_nr),
        ]

        # wire up DAC/ADC
        m.d.comb += [
            dac.stream_in.stream_eq(dac_extractor.channel_stream_out),

            # wire up DAC/ADC
            # in I2S, everything happens on the negedge
            # the easiest way to achieve this, is to invert
            # the clock signal
            dac_pads.sclk.eq(~ClockSignal("adat")),
            dac_pads.bclk.eq(~ClockSignal("dac")),
            dac_pads.lrclk.eq(~lrclk),
            dac_pads.data.eq(dac.serial_data_out),
            dac.enable_in.eq(1),

            # wire up I2S transmitter
            dac.word_select_in.eq(~lrclk),
            dac.serial_clock_in.eq(~ClockSignal("dac")),
        ]

if __name__ == "__main__":
    os.environ["LUNA_PLATFORM"] = "platforms:ADATFaceCycloneIV"
    #os.environ["LUNA_PLATFORM"] = "platforms:ADATFaceCycloneV"
    #os.environ["LUNA_PLATFORM"] = "platforms:ADATFaceCyclone10"
    top_level_cli(USB2AudioInterface)