# ADAT USB Audio Interface

FPGA based USB 2.0 High Speed audio interface featuring multiple optical ADAT inputs and outputs

## Status / current limitations
* enumerates as class compliant audio device on Linux (Windows only with 2 channels)
* audio output works with glitches (sample rate feedback buggy)
* only 48kHz sample rate supported
* audio input is still a dummy (internally generated signal)
* integrated USB2 high speed logic analyzer works