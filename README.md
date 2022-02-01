# ADAT USB Audio Interface

FPGA based USB 2.0 High Speed audio interface featuring multiple optical ADAT inputs and outputs

![BlockDiagram](https://user-images.githubusercontent.com/148607/149699910-284d7113-11b3-4edd-9c6e-68ed0b58e31d.png)

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
* Limitation: Currently audio input will not work properly when audio output is inactive.
  This should not be a problem for most uses (VoIP, Videoconference, DAW recording).
  If you have an important use case which needs this, please file an issue.

## Hardware
The current board design is a custom development board,
based on the QMTech core FPGA boards.
Once the chip shortage is over, it is planned to move to
a complete custom design, including the FPGA.

![P1173938](https://user-images.githubusercontent.com/148607/149684388-dc81b2b4-235a-4fb7-9b58-c8799dd494fb.jpg)

![image](https://user-images.githubusercontent.com/148607/149700539-21e60090-d90e-4338-9a27-27a406f1c2f6.png)

## How to build
1. Download and install [Intel Quartus Lite](https://fpgasoftware.intel.com/?edition=lite)
2. put the bin/ directory of Quartus into your PATH variable:
```bash
export PATH=$PATH:/opt/intelFPGA_lite/21.1/quartus/bin/
```
Of course you need to adjust this to the install directory and version of your particular installation.

3. Set up python venv and install requirements:
```bash
$ cd gateware/
$ ./initialize-python-environment.sh
$ cd ..
```

4. Activate the venv and build
```bash
$ source ./gateware/venv/bin/activate
$ python3 gateware/adat_usb2_audio_interface.py --keep
```

This will create a directory named build/ and after a successful build will directly
try to load the generated bitstream into the FPGA, if an USB-Blaster is connected.
Or, you can flash the bitstream manually, by opening the Quartus GUI with:
```bash
quartus build/*.qpf
```
and then open the programmer application from there.
Alternatively you could directly start the programmer with:
```bash
quartus_pgmw
```
