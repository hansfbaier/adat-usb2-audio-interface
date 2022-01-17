# ADAT USB Audio Interface

FPGA based USB 2.0 High Speed audio interface featuring multiple optical ADAT inputs and outputs

![BlockDiagram](https://user-images.githubusercontent.com/148607/149699649-b56460cb-9bc5-4459-bf49-5454ceee18dc.png)

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
* The current board design has not been designed with the case in mind: In the current version of the case,
  only ADAT-cables with thin connectors will fit into the holes. Cables with fat connectors will hit the case
  wall before they can be fully inserted. This will be fixed in a future iteration of the PCB and case.
* The current case design lacks a guide channel for the LED light pipes. Therefore there is considerable bleed
  from lightpipes into each other, and they also can't be positioned exactly over the LEDs.
  Will be fixed in the next version of the case.

## Hardware
The current board design is a custom development board,
based on the QMTech core FPGA boards.
Once the chip shortage is over, it is planned to move to
a complete custom design, including the FPGA.

![P1173938](https://user-images.githubusercontent.com/148607/149684388-dc81b2b4-235a-4fb7-9b58-c8799dd494fb.jpg)


