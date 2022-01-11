# ADAT USB Audio Interface

FPGA based USB 2.0 High Speed audio interface featuring multiple optical ADAT inputs and outputs

## Status / current limitations
* Enumerates as class compliant audio device on Windows and Linux (Mac OS not tested). 2 and 32 channel modes.
* Audio input and output seems to work glitch free.
* Only 48kHz sample rate supported
* Integrated USB2 high speed logic analyzer works
* Runs without dropouts with FlexASIO with a buffer size of 32 samples (0.67ms latency)
* Has a hardware roundtrip latency (USB out -> ADAT out -> cable -> ADAT in -> USB in)
  of 2-3 USB2 microframes which is about 0.25ms to 0.375 ms
* Both headphone DACs on the board work now. In two channel mode, they are both wired to channels 0/1.
  In 36 channel mode DAC1 is wired to channels 0/1 and DAC2 to channels 2/3
* Both USB PHYs now are operational. USB1 has access to all 32 ADAT I/Os and has 4 extra channels to/from USB2.
  USB2 enumerates as a 4-channel sound card which sends/receives audio to/from USB1
* Both USB interfaces will also enumerate as USB MIDI devices and send each other MIDI

## Hardware
The current board design is a custom development board,
based on the QMTech core FPGA boards.
Once the chip shortage is over, it is planned to move to
a complete custom design, including the FPGA.

### Bare PCB as assembled by JLCPCB:
![FDZ-uphVgAgb0UV](https://user-images.githubusercontent.com/148607/141603571-2741a7d5-d088-4447-9aad-edc82d864e0f.jpeg)

### PCB in functional state:
![FDaPZ3DVkAMLve-](https://user-images.githubusercontent.com/148607/141603557-2b68c49f-0734-433a-92e7-d26bea887b8b.jpeg)


