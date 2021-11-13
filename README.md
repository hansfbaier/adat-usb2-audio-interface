# ADAT USB Audio Interface

FPGA based USB 2.0 High Speed audio interface featuring multiple optical ADAT inputs and outputs

## Status / current limitations
* enumerates as class compliant audio device on Windows and Linux (Mac OS not tested). 2 and 8 channel modes.
* audio output works almost glitch free. Occasional underruns occur, but they are barely audible.
* only 48kHz sample rate supported
* audio input (recording) works with glitches
* integrated USB2 high speed logic analyzer works

## Hardware
The current board design is a custom development board,
based on the QMTech core FPGA boards.
Once the chip shortage is over, it is planned to move to
a complete custom design, including the FPGA.

### Bare PCB as assembled by JLCPCB:
![FDZ-uphVgAgb0UV](https://user-images.githubusercontent.com/148607/141603571-2741a7d5-d088-4447-9aad-edc82d864e0f.jpeg)

### PCB in functional state:
![FDaPZ3DVkAMLve-](https://user-images.githubusercontent.com/148607/141603557-2b68c49f-0734-433a-92e7-d26bea887b8b.jpeg)


