from amaranth import *
from amaranth.lib.cdc    import FFSynchronizer, PulseSynchronizer

from amlib.debug.ila     import StreamILA, ILACoreParameters
from amlib.stream        import StreamInterface
from amlib.io.led        import NumberToBitBar
from amlib.io.max7219    import SerialLEDArray

from luna.gateware.usb.usb2.endpoints.stream  import USBMultibyteStreamInEndpoint

def add_debug_led_array(v):
    self                      = v['self']
    m                         = v['m']
    platform                  = v['platform']
    channels_to_usb1_stream   = v['channels_to_usb1_stream']
    input_to_usb_fifo         = v['input_to_usb_fifo']
    usb1_to_output_fifo_level = v['usb1_to_output_fifo_level']
    usb1_to_output_fifo_depth = v['usb1_to_output_fifo_depth']
    usb2_to_usb1_fifo_level   = v['usb2_to_usb1_fifo_level']
    usb2_to_usb1_fifo_depth   = v['usb2_to_usb1_fifo_depth']
    channels_to_usb2_stream   = v['channels_to_usb2_stream']
    usb2_audio_out_active     = v['usb2_audio_out_active']
    usb2_audio_in_active      = v['usb2_audio_in_active']
    bundle_multiplexer        = v['bundle_multiplexer']
    adat_transmitters         = v['adat_transmitters']
    usb1_to_usb2_midi_fifo    = v['usb1_to_usb2_midi_fifo']
    usb2_to_usb1_midi_fifo    = v['usb2_to_usb1_midi_fifo']


    adat1_underflow_count = Signal(16)
    with m.If(adat_transmitters[0].underflow_out):
        m.d.sync += adat1_underflow_count.eq(adat1_underflow_count + 1)

    spi = platform.request("spi")
    m.submodules.led_display  = led_display = SerialLEDArray(divisor=10, init_delay=24e6, no_modules=2)

    rx_level_bars = []
    for i in range(1, 5):
        rx_level_bar = NumberToBitBar(0, bundle_multiplexer.FIFO_DEPTH, 8)
        setattr(m.submodules, f"rx{i}_level_bar", rx_level_bar)
        m.d.comb += rx_level_bar.value_in.eq(bundle_multiplexer.levels[i - 1])
        rx_level_bars.append(rx_level_bar)

    m.submodules.in_bar       = in_to_usb_fifo_bar  = NumberToBitBar(0, self.INPUT_CDC_FIFO_DEPTH, 8)
    m.submodules.in_fifo_bar  = channels_to_usb_bar = NumberToBitBar(0, 2 * self.USB1_MAX_PACKET_SIZE, 8)
    m.submodules.out_fifo_bar = out_fifo_bar        = NumberToBitBar(0, usb1_to_output_fifo_depth, 8)

    m.d.comb += [
        # LED bar displays
        in_to_usb_fifo_bar.value_in.eq(input_to_usb_fifo.r_level),
        channels_to_usb_bar.value_in.eq(channels_to_usb1_stream.level >> 3),
        out_fifo_bar.value_in.eq(usb1_to_output_fifo_level >> 1),

        *[led_display.digits_in[i].eq(Cat(reversed(rx_level_bars[i].bitbar_out))) for i in range(4)],
        led_display.digits_in[4].eq(Cat(reversed(in_to_usb_fifo_bar.bitbar_out))),
        led_display.digits_in[5].eq(Cat(reversed(channels_to_usb_bar.bitbar_out))),
        led_display.digits_in[6].eq(Cat(reversed(out_fifo_bar.bitbar_out))),
        led_display.digits_in[7].eq(adat1_underflow_count),
    ]

    usb2 = lambda x: 8 + x

    m.submodules.usb2_output_fifo_bar = usb2_output_fifo_bar = NumberToBitBar(0, usb2_to_usb1_fifo_depth, 8)
    m.submodules.usb2_input_fifo_bar  = usb2_input_fifo_bar  = NumberToBitBar(0, channels_to_usb2_stream._fifo_depth, 8)

    m.d.comb += [
        usb2_output_fifo_bar.value_in.eq(usb2_to_usb1_fifo_level),
        usb2_input_fifo_bar.value_in.eq(channels_to_usb2_stream.level),
        led_display.digits_in[usb2(0)][0].eq(usb2_audio_out_active),
        led_display.digits_in[usb2(0)][7].eq(usb2_audio_in_active),
        led_display.digits_in[usb2(1)].eq(Cat(usb2_output_fifo_bar.bitbar_out)),
        led_display.digits_in[usb2(2)].eq(Cat(reversed(usb2_input_fifo_bar.bitbar_out))),
        led_display.digits_in[usb2(3)].eq(usb1_to_usb2_midi_fifo.level),
        led_display.digits_in[usb2(4)].eq(usb2_to_usb1_midi_fifo.level),
    ]

    m.d.comb += [
        *led_display.connect_to_resource(spi),
        led_display.valid_in.eq(1),
    ]


def setup_ila(v, ila_max_packet_size):
    m                            = v['m']
    usb1_sof_counter             = v['usb1_sof_counter']
    usb1                         = v['usb1']
    ep1_out                      = v['usb2_ep1_out']
    ep2_in                       = v['usb2_ep2_in']
    usb2_audio_out_active        = v['usb2_audio_out_active']
    usb1_audio_in_active         = v['usb1_audio_in_active']
    channels_to_usb_stream       = v['channels_to_usb2_stream']
    usb_to_channel_stream        = v['usb2_to_channel_stream']
    input_to_usb_fifo            = v['input_to_usb_fifo']
    usb1_to_output_fifo          = v['usb1_to_output_fifo']
    usb1_to_output_fifo_level    = v['usb1_to_output_fifo_level']
    usb1_to_output_fifo_depth    = v['usb1_to_output_fifo_depth']
    audio_in_frame_bytes         = v['usb2_audio_in_frame_bytes']
    min_fifo_level               = v['min_fifo_level']
    max_fifo_level               = v['max_fifo_level']
    adat_transmitters            = v['adat_transmitters']
    adat_receivers               = v['adat_receivers']
    bundle_demultiplexer         = v['bundle_demultiplexer']
    bundle_multiplexer           = v['bundle_multiplexer']
    usb1_channel_stream_combiner = v['usb1_channel_stream_combiner']
    usb1_channel_stream_splitter = v['usb1_channel_stream_splitter']
    usb2_ep3_in                  = v['usb2_ep3_in']
    usb2_ep3_out                 = v['usb2_ep3_out']
    usb1_to_usb2_midi_fifo       = v['usb1_to_usb2_midi_fifo']
    usb2_to_usb1_midi_fifo       = v['usb2_to_usb1_midi_fifo']

    adat_clock = Signal()
    m.d.comb += adat_clock.eq(ClockSignal("adat"))
    sof_wrap = Signal()
    m.d.comb += sof_wrap.eq(usb1_sof_counter == 0)

    usb_packet_counter = Signal(10)
    with m.If(ep1_out.stream.valid & ep1_out.stream.ready):
        m.d.usb += usb_packet_counter.eq(usb_packet_counter + 1)
        with m.If(ep1_out.stream.last):
            m.d.usb += usb_packet_counter.eq(0)

    weird_packet = Signal()
    m.d.comb += weird_packet.eq(ep1_out.stream.last & (
        usb_packet_counter[0:2] != Const(0b11, 2)
    ))

    strange_input          = Signal()
    input_active           = Signal()
    output_active          = Signal()
    input_or_output_active = Signal()
    garbage                = Signal()
    usb_frame_borders      = Signal()

    m.d.comb += [
        input_active.eq (  channels_to_usb_stream.channel_stream_in.ready
                            & channels_to_usb_stream.channel_stream_in.valid),
        output_active.eq(  channels_to_usb_stream.usb_stream_out.ready
                            & channels_to_usb_stream.usb_stream_out.valid),
        input_or_output_active.eq(input_active | output_active),

        strange_input.eq(  (channels_to_usb_stream.channel_stream_in.payload != 0)
                            & (channels_to_usb_stream.channel_stream_in.channel_nr > 1)),
        garbage.eq(channels_to_usb_stream.skipping | channels_to_usb_stream.filling),
        usb_frame_borders.eq(ep2_in.data_requested | ep2_in.frame_finished),
    ]

    fill_count = Signal(16)
    with m.If(channels_to_usb_stream.filling):
        m.d.usb += fill_count.eq(fill_count + 1)

    channels_to_usb_input_frame = [
        usb1.sof_detected,
        input_to_usb_fifo.r_level,
        channels_to_usb_stream.channel_stream_in.channel_nr,
        channels_to_usb_stream.channel_stream_in.first,
        channels_to_usb_stream.channel_stream_in.last,
        input_active,
        #channels_to_usb_stream.channel_stream_in.payload,
    ]

    weird_frame_size = Signal()
    usb_outputting   = Signal()
    m.d.comb += usb_outputting.eq(ep1_out.stream.valid & ep1_out.stream.ready)

    usb_out_level_maxed = Signal()
    m.d.comb += usb_out_level_maxed.eq(usb1_to_output_fifo_level >= (usb1_to_output_fifo_depth - 1))

    m.d.comb += weird_frame_size.eq((audio_in_frame_bytes & 0b11) != 0)

    channels_to_usb_debug = [
        usb2_audio_out_active,
        audio_in_frame_bytes,
        channels_to_usb_stream.current_channel,
        channels_to_usb_stream.channel_stream_in.ready,
        channels_to_usb_stream.level,
        channels_to_usb_stream.fifo_full,
        channels_to_usb_stream.fifo_level_insufficient,
        channels_to_usb_stream.out_channel,
        channels_to_usb_stream.fifo_read,
        channels_to_usb_stream.usb_channel,
        channels_to_usb_stream.done,
        channels_to_usb_stream.usb_byte_pos,
        channels_to_usb_stream.skipping,
        channels_to_usb_stream.filling,
        ep2_in.data_requested,
        ep2_in.frame_finished,
        channels_to_usb_stream.usb_stream_out.valid,
        channels_to_usb_stream.usb_stream_out.ready,
        channels_to_usb_stream.usb_stream_out.first,
        channels_to_usb_stream.usb_stream_out.last,
        channels_to_usb_stream.usb_stream_out.payload,
    ]

    usb_out_debug = [
        usb_to_channel_stream.channel_stream_out.payload,
        usb_to_channel_stream.channel_stream_out.channel_nr,
        usb_to_channel_stream.channel_stream_out.first,
        usb_to_channel_stream.channel_stream_out.last,
        #usb1_to_output_fifo_level,
        #usb_out_level_maxed
    ]

    usb_channel_outputting = Signal()
    m.d.comb += usb_channel_outputting.eq(
        usb_out_level_maxed |
        usb_to_channel_stream.channel_stream_out.first |
        usb_to_channel_stream.channel_stream_out.last  |
            ( usb_to_channel_stream.channel_stream_out.ready &
                usb_to_channel_stream.channel_stream_out.valid)
        )

    ep1_out_fifo_debug = [
        audio_in_frame_bytes,
        min_fifo_level,
        usb1_to_output_fifo_level,
        max_fifo_level,
        usb1.sof_detected,
    ]

    adat_nr = 0
    receiver_debug = [
        adat_receivers[adat_nr].sample_out,
        adat_receivers[adat_nr].addr_out,
        adat_receivers[adat_nr].output_enable,
        #adat_receivers[adat_nr].recovered_clock_out,
    ]

    adat_first = Signal()
    m.d.comb += adat_first.eq(adat_receivers[adat_nr].output_enable & (adat_receivers[adat_nr].addr_out == 0))
    adat_clock = Signal()
    m.d.comb += adat_clock.eq(ClockSignal("adat"))

    adat_debug = [
        adat_clock,
        adat_transmitters[adat_nr].adat_out,
        adat_receivers[adat_nr].recovered_clock_out,
        adat_receivers[adat_nr].adat_in,
        adat_first,
        adat_receivers[adat_nr].output_enable,
    ]

    adat_transmitter_debug = [
        adat_clock,
        bundle_demultiplexer.bundles_out[adat_nr].channel_nr,
        adat_transmitters[adat_nr].sample_in,
        adat_transmitters[adat_nr].valid_in,
        adat_transmitters[adat_nr].last_in,
        adat_transmitters[adat_nr].ready_out,
        adat_transmitters[adat_nr].fifo_level_out,
        adat_transmitters[adat_nr].underflow_out,
        adat_transmitters[adat_nr].adat_out,
    ]

    bundle0_active            = Signal()
    bundle3_active            = Signal()
    bundle_multiplexer_active = Signal()
    multiplexer_enable        = Signal()

    m.d.comb += [
        bundle0_active.eq((bundle_multiplexer.bundles_in[0].valid &
                            bundle_multiplexer.bundles_in[0].ready)),
        bundle3_active.eq((bundle_multiplexer.bundles_in[3].valid &
                            bundle_multiplexer.bundles_in[3].ready)),
        bundle_multiplexer_active.eq((bundle_multiplexer.channel_stream_out.valid &
                                        bundle_multiplexer.channel_stream_out.ready)),
        multiplexer_enable.eq(bundle0_active | bundle3_active | bundle_multiplexer_active),
    ]

    multiplexer_debug = [
        bundle_multiplexer.current_bundle,
        bundle_multiplexer.last_bundle,
        bundle0_active,
        #bundle_multiplexer.bundles_in[0].payload,
        bundle_multiplexer.bundles_in[0].channel_nr,
        bundle_multiplexer.bundles_in[0].last,
        bundle3_active,
        #bundle_multiplexer.bundles_in[3].payload,
        bundle_multiplexer.bundles_in[3].channel_nr,
        bundle_multiplexer.bundles_in[3].last,
        #bundle_multiplexer.channel_stream_out.payload,
        bundle_multiplexer_active,
        bundle_multiplexer.channel_stream_out.channel_nr,
        bundle_multiplexer.channel_stream_out.last,
        input_to_usb_fifo.w_level,
    ]

    demultiplexer_debug = [
        bundle_demultiplexer.channel_stream_in.ready,
        bundle_demultiplexer.channel_stream_in.valid,
        bundle_demultiplexer.channel_stream_in.channel_nr,
        #bundle_demultiplexer.channel_stream_in.payload,
        *[bundle_demultiplexer.bundles_out[i].ready for i in range(4)],
        *[bundle_demultiplexer.bundles_out[i].valid for i in range(4)],
        *[bundle_demultiplexer.bundles_out[i].channel_nr for i in range(4)],
    ]

    demultiplexer_enable = Signal()
    m.d.comb += demultiplexer_enable.eq(
        (bundle_demultiplexer.bundles_out[0].valid &
            bundle_demultiplexer.bundles_out[0].ready) |
        (bundle_demultiplexer.bundles_out[3].valid &
            bundle_demultiplexer.bundles_out[3].ready) |
        (bundle_demultiplexer.channel_stream_in.valid &
            bundle_demultiplexer.channel_stream_in.ready)
    )

    levels = [
        input_to_usb_fifo.r_level,
        channels_to_usb_stream.level,
    ]

    adat_transmit_count       = Signal(8)
    adat_transmit_frames      = Signal.like(adat_transmit_count)
    adat_receiver0_count      = Signal.like(adat_transmit_count)
    adat_receiver0_frames     = Signal.like(adat_transmit_count)
    adat_receiver3_count      = Signal.like(adat_transmit_count)
    adat_receiver3_frames     = Signal.like(adat_transmit_count)
    adat_multiplexer_count    = Signal.like(adat_transmit_count)
    adat_multiplexer_frames   = Signal.like(adat_transmit_count)
    adat_channels2usb_count   = Signal.like(adat_transmit_count)
    adat_channels2usb_frames  = Signal.like(adat_transmit_count)
    usb_receive_frames        = Signal.like(adat_transmit_count)

    m.submodules.sof_synchronizer = sof_synchronizer = PulseSynchronizer("usb", "fast")
    sof_fast                    = Signal()
    adat_receiver0_fast         = Signal()
    adat_receiver3_fast         = Signal()
    adat_multiplexer_out_fast   = Signal()

    m.d.comb += [
        sof_synchronizer.i.eq(usb1.sof_detected),
        sof_fast.eq(sof_synchronizer.o),

        adat_receiver0_fast.eq((adat_receivers[0].addr_out == 7) & adat_receivers[0].output_enable),
        adat_receiver3_fast.eq((adat_receivers[3].addr_out == 7) & adat_receivers[3].output_enable),
        adat_multiplexer_out_fast.eq(bundle_multiplexer.channel_stream_out.ready & bundle_multiplexer.channel_stream_out.valid & bundle_multiplexer.channel_stream_out.last),
    ]

    with m.If(sof_fast):
        m.d.fast += [
            adat_receiver0_frames.eq(adat_receiver0_count),
            adat_receiver0_count.eq(0),
            adat_receiver3_frames.eq(adat_receiver3_count),
            adat_receiver3_count.eq(0),
            adat_multiplexer_frames.eq(adat_multiplexer_count),
            adat_multiplexer_count.eq(0),
        ]

    with m.If(adat_receiver0_fast):
        m.d.fast += adat_receiver0_count.eq(adat_receiver0_count + 1)

    with m.If(adat_receiver3_fast):
        m.d.fast += adat_receiver3_count.eq(adat_receiver3_count + 1)

    with m.If(adat_multiplexer_out_fast):
        m.d.fast += adat_multiplexer_count.eq(adat_multiplexer_count + 1)

    frame_counts = [
        adat_transmit_frames,
        adat_receiver0_frames,
        adat_receiver3_frames,
        adat_multiplexer_frames,
        adat_channels2usb_frames,
        usb_receive_frames,
    ]

    with m.If(channels_to_usb_stream.channel_stream_in.last & channels_to_usb_stream.channel_stream_in.valid & channels_to_usb_stream.channel_stream_in.ready):
        m.d.usb += adat_channels2usb_count.eq(adat_channels2usb_count + 1)

    with m.If(usb_to_channel_stream.channel_stream_out.last & usb_to_channel_stream.channel_stream_out.valid & usb_to_channel_stream.channel_stream_out.ready):
        m.d.usb += adat_transmit_count.eq(adat_transmit_count + 1)

    with m.If(usb1.sof_detected):
        m.d.usb += [
            adat_transmit_frames.eq(adat_transmit_count),
            adat_transmit_count.eq(0),
            adat_channels2usb_frames.eq(adat_channels2usb_count),
            adat_channels2usb_count.eq(0),
            usb_receive_frames.eq(audio_in_frame_bytes >> 7),
        ]

    channel_stream_combiner_debug = [
        #usb1_channel_stream_combiner.lower_channel_stream_in.valid,
        #usb1_channel_stream_combiner.lower_channel_stream_in.ready,
        #usb1_channel_stream_combiner.lower_channel_stream_in.payload,
        #usb1_channel_stream_combiner.lower_channel_stream_in.channel_nr,
        #usb1_channel_stream_combiner.lower_channel_stream_in.first,
        #usb1_channel_stream_combiner.lower_channel_stream_in.last,
        usb2_audio_out_active,
        usb1_channel_stream_combiner.upper_channel_stream_in.valid,
        usb1_channel_stream_combiner.upper_channel_stream_in.ready,
        usb1_channel_stream_combiner.upper_channel_stream_in.payload,
        usb1_channel_stream_combiner.upper_channel_stream_in.channel_nr,
        usb1_channel_stream_combiner.upper_channel_stream_in.first,
        usb1_channel_stream_combiner.upper_channel_stream_in.last,
        usb1_channel_stream_combiner.upper_channel_counter,
        usb1_channel_stream_combiner.state,
        #usb1_channel_stream_combiner.combined_channel_stream_out.valid,
        #usb1_channel_stream_combiner.combined_channel_stream_out.ready,
        #usb1_channel_stream_combiner.combined_channel_stream_out.payload,
        #usb1_channel_stream_combiner.combined_channel_stream_out.channel_nr,
        #usb1_channel_stream_combiner.combined_channel_stream_out.first,
        #usb1_channel_stream_combiner.combined_channel_stream_out.last,
    ]

    upper_channel_active = Signal()
    channel_stream_combiner_active = Signal()
    m.d.comb += [
        upper_channel_active.eq(usb1_channel_stream_combiner.upper_channel_stream_in.valid &
                                usb1_channel_stream_combiner.upper_channel_stream_in.ready),
        channel_stream_combiner_active.eq(
            upper_channel_active |
            (usb1_channel_stream_combiner.combined_channel_stream_out.valid &
            usb1_channel_stream_combiner.combined_channel_stream_out.ready) |
            (usb1_channel_stream_combiner.lower_channel_stream_in.valid &
            usb1_channel_stream_combiner.lower_channel_stream_in.ready))
    ]

    channel_stream_splitter_debug = [
        usb1_channel_stream_splitter.lower_channel_stream_out.valid,
        usb1_channel_stream_splitter.lower_channel_stream_out.ready,
        usb1_channel_stream_splitter.lower_channel_stream_out.payload,
        usb1_channel_stream_splitter.lower_channel_stream_out.channel_nr,
        usb1_channel_stream_splitter.lower_channel_stream_out.first,
        usb1_channel_stream_splitter.lower_channel_stream_out.last,
        usb2_audio_out_active,
        usb1_channel_stream_splitter.upper_channel_stream_out.valid,
        usb1_channel_stream_splitter.upper_channel_stream_out.ready,
        usb1_channel_stream_splitter.upper_channel_stream_out.payload,
        usb1_channel_stream_splitter.upper_channel_stream_out.channel_nr,
        usb1_channel_stream_splitter.upper_channel_stream_out.first,
        usb1_channel_stream_splitter.upper_channel_stream_out.last,
        usb1_channel_stream_splitter.combined_channel_stream_in.valid,
        usb1_channel_stream_splitter.combined_channel_stream_in.ready,
        usb1_channel_stream_splitter.combined_channel_stream_in.payload,
        usb1_channel_stream_splitter.combined_channel_stream_in.channel_nr,
        usb1_channel_stream_splitter.combined_channel_stream_in.first,
        usb1_channel_stream_splitter.combined_channel_stream_in.last,
    ]

    splitter_upper_channel_active = Signal()
    channel_stream_splitter_active = Signal()
    m.d.comb += [
        splitter_upper_channel_active.eq(usb1_channel_stream_splitter.upper_channel_stream_out.valid &
                                            usb1_channel_stream_splitter.upper_channel_stream_out.ready),
        channel_stream_splitter_active.eq(
            splitter_upper_channel_active |
            (usb1_channel_stream_splitter.combined_channel_stream_in.valid &
                usb1_channel_stream_splitter.combined_channel_stream_in.ready) |
            (usb1_channel_stream_splitter.lower_channel_stream_out.valid &
                usb1_channel_stream_splitter.lower_channel_stream_out.ready))
    ]

    midi_in_active = Signal()
    m.d.comb += midi_in_active.eq(usb2_ep3_in.stream.valid & usb2_ep3_in.stream.ready)
    midi_out_active = Signal()
    m.d.comb += midi_out_active.eq(usb2_ep3_out.stream.valid & usb2_ep3_out.stream.ready)
    midi_active = Signal()
    m.d.comb += midi_active.eq(midi_in_active | midi_out_active)

    midi_out_stream = StreamInterface(name="midi_out")
    m.d.comb += midi_out_stream.stream_eq(usb2_ep3_out.stream, omit="ready")
    midi_in_stream = StreamInterface(name="midi_in")
    m.d.comb += midi_in_stream.stream_eq(usb2_ep3_in.stream, omit="ready")

    midi_out = [
        usb2_ep3_out.stream.ready,
        usb2_ep3_out.stream.valid,
        midi_out_stream.payload,
        midi_out_stream.first,
        midi_out_stream.last,
        usb2_to_usb1_midi_fifo.r_level,
    ]

    #
    # signals to trace
    #
    signals = midi_out

    signals_bits = sum([s.width for s in signals])
    m.submodules.ila = ila = \
        StreamILA(
            domain="usb", o_domain="usb",
            sample_rate=60e6, # usb domain
            #sample_rate=48e3 * 256 * 5, # sync domain
            #sample_rate=48e3 * 256 * 9, # fast domain
            signals=signals,
            sample_depth       = int(10 * 8 * 1024 / signals_bits),
            samples_pretrigger = 2, #int(78 * 8 * 1024 / signals_bits),
            with_enable=False)

    stream_ep = USBMultibyteStreamInEndpoint(
        endpoint_number=4, # EP 4 IN
        max_packet_size=ila_max_packet_size,
        byte_width=ila.bytes_per_sample
    )
    usb1.add_endpoint(stream_ep)

    m.d.comb += [
        stream_ep.stream.stream_eq(ila.stream),
        # ila.enable.eq(input_or_output_active | garbage | usb_frame_borders),
        ila.trigger.eq(midi_out_active),
        #ila.enable .eq(midi_out_active),
    ]

    ILACoreParameters(ila).pickle()

