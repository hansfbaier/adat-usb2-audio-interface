TARGET      = firmware
BAUDRATE    = 115200
SERIALPORT ?= /dev/ttyACM0

CROSS  ?= riscv64-unknown-elf-

CC      = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy

CFLAGS  = -march=rv32i -mabi=ilp32 -g -Os -Wall -Werror
LDFLAGS = -Tsoc.ld -Triscv_standalone.ld  -nostdlib

SOURCES = \
	start.S \
	$(TARGET).c


# By default, build our binary.
all: $(TARGET).bin

#
# Firmware binary.
#

$(TARGET).elf: $(SOURCES) soc.ld resources.h
	$(CC) $(CFLAGS) $(LDFLAGS) $(SOURCES) -o $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@


#
# Virtual/command targets.
#

.PHONY: clean

clean:
	rm -f $(TARGET).elf $(TARGET).bin
