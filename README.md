# ADAT USB Audio Interface

FPGA based USB 2.0 High Speed audio interface featuring multiple optical ADAT inputs and outputs

## Status / current limitations
* enumerates as class compliant audio device on Windows and Linux (Mac OS not tested). 2 and 32 channel modes.
* audio input and output seems to work glitch free.
* only 48kHz sample rate supported
* integrated USB2 high speed logic analyzer works
* runs without dropouts with FlexASIO with a buffer size of 32 samples (0.67ms latency)
* has a hardware roundtrip latency (USB out -> ADAT out -> cable -> ADAT in -> USB in)
  of 2-3 USB2 microframes which is about 0.25ms to 0.375 ms

## Hardware
The current board design is a custom development board,
based on the QMTech core FPGA boards.
Once the chip shortage is over, it is planned to move to
a complete custom design, including the FPGA.

### Bare PCB as assembled by JLCPCB:
![FDZ-uphVgAgb0UV](https://user-images.githubusercontent.com/148607/141603571-2741a7d5-d088-4447-9aad-edc82d864e0f.jpeg)

### PCB in functional state:
![FDaPZ3DVkAMLve-](https://user-images.githubusercontent.com/148607/141603557-2b68c49f-0734-433a-92e7-d26bea887b8b.jpeg)


