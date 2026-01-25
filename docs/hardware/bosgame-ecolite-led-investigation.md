# BOSGAME Ecolite LED Ring Light Investigation

## Overview

The BOSGAME Ecolite Series (DNB10M) mini PC at `pve.maas` has a circular RGB ring light on top that runs a rainbow animation by default. This document records attempts to control it from Linux.

**Result: FAILED - No working method found. LED control remains unknown.**

## Hardware Information

| Property | Value |
|----------|-------|
| Manufacturer | BOSGAME |
| Product | Ecolite Series |
| Family | DNB10M |
| Serial | ME10241002219 |
| CPU | Intel Alder Lake-N (N100) |
| EC Chip | ITE IT5570E |
| LED Type | Circular RGB ring on top |
| Default Mode | Rainbow cycling animation |

## What We Tried

### 1. EC Register Probing

The IT5570E Embedded Controller exposes registers via `/sys/kernel/debug/ec/ec0/io`.

```bash
# Enable EC write support
modprobe ec_sys write_support=1

# Dump EC registers
xxd /sys/kernel/debug/ec/ec0/io
```

**Non-zero registers found:**
- 0x00: 0x01
- 0x01: 0x03
- 0x04: 0x01
- 0x09: 0xdd
- 0x46: 0x01
- 0x62: 0x1a (temperature?)
- 0x70: 0x2c
- 0x72: 0x18-0x19 (fluctuating - temperature)
- 0x7f: 0x01
- 0x80: 0x02
- 0x81: 0x01
- 0x8c: 0x01
- 0xa0-a3: 0x03, 0x01, 0x01, 0x01

**Tested writing to:** 0x00, 0x46, 0xa0
**Result:** No effect on LED

### 2. ACPI/DSDT Analysis

Decompiled DSDT with `iasl -d dsdt.dat` and searched for LED references.

**Found:**
- `RGBC` field at offset 0x921 in GNVS (Global NVS) SystemMemory region
- `RGBE` bit field (enable flag?)
- `LEDU` 16-bit field
- `DLED` variable in EC device

**GNVS base:** 0x67241000
**RGBC offset:** 0x921
**RGBC address:** 0x67241921

```bash
# Read RGBC value
dd if=/dev/mem bs=1 skip=$((0x67241921)) count=1 2>/dev/null | xxd -p
# Result: 00
```

**Result:** RGBC was 0x00, no methods in DSDT actually use these fields for LED control.

### 3. GPIO Probing

Found 360 GPIO lines via `gpioinfo`. Tested output pins that could be RGB (160-162, 226-230).

```bash
# Toggle potential LED pins
gpioset gpiochip0 160=0 161=0 162=0  # All off
gpioset gpiochip0 160=1 161=1 162=1  # All on
```

**Result:** No effect on LED

### 4. I2C Device Scan

```bash
i2cdetect -y 0
```

**Devices found on SMBus (bus 0):**
- 0x08: Unknown (read failed)
- 0x30, 0x31, 0x34, 0x35: Unknown (read failed)
- 0x36, 0x37: dummy driver
- 0x44: Responds to reads
- 0x50: EEPROM (ee1004)

### 5. I2C 0x44 Write Attempt - CRASHED SYSTEM

**WARNING: DO NOT WRITE TO I2C 0x44**

```bash
# THIS CRASHED THE SYSTEM
i2cset -y 0 0x44 0x00 0x01
```

**Result:** System froze immediately. Required power cycle. OPNsense VM failed to start after reboot due to separate misconfiguration issue.

Device 0x44 is likely a power management or system controller - NOT an LED controller.

### 6. OpenRGB

```bash
apt install openrgb
openrgb --list-devices
```

**Result:** No devices detected. OpenRGB doesn't support this hardware.

### 7. USB Serial (CH340) Check

Many mini PC LED controllers use USB-to-serial (CH340) chips.

```bash
lsusb | grep -i ch340
ls /dev/ttyUSB*
```

**Result:** No CH340 or USB serial devices present. LED is not controlled via USB serial.

### 8. PWM Check

```bash
ls /sys/class/pwm/
cat /sys/class/pwm/pwmchip0/npwm
```

**Result:** 1 PWM channel exists (for fan or backlight), not RGB LED.

### 9. CYX_RGB_LED_Tool Analysis

Downloaded and reverse-engineered the CYX_RGB_LED_Tool used by similar mini PCs (AM08 Pro).

**Key findings from disassembly:**
- Uses `io.dll` (inpout32) for direct I/O port access
- Functions: `Out32`, `Inp32`, `IsInpOutDriverOpen`
- Reads ports 0x2000/0x2001 for chip detection, expects 0x55 and 0x70/0x71
- Built for **IT5571** chip (different from IT5570E)
- Uses ports 0xC400 or 0x400 for LED control

**Testing on BOSGAME:**
```bash
# Read detection ports
python3 -c "import os; fd=os.open('/dev/port',os.O_RDONLY); os.lseek(fd,0x2000,0); print(hex(os.read(fd,1)[0]))"
# Result: 0xff (not responding)
```

**Result:** CYX tool is incompatible - different chip, different protocol.

## EC Port Configuration

From `/proc/ioports`:
```
0062-0062 : EC data
0066-0066 : EC cmd
2000-20fe : pnp 00:04
```

The BOSGAME uses standard EC ports (0x62/0x66), not the extended ports the CYX tool expects.

## Conclusions

1. **No Linux driver exists** for IT5570E LED control
2. **No BOSGAME LED software** found online
3. **EC registers 0x00-0xFF** don't control the LED
4. **LED control is likely in:**
   - Extended EC RAM (0x100+ range, not easily accessible)
   - Separate microcontroller not exposed to OS
   - EC firmware handling animation internally

## Recommendations

1. **Accept the rainbow** - it looks fine
2. **Check BIOS** - some mini PCs have LED settings in UEFI
3. **Email BOSGAME support** - ask for LED control software
4. **Boot Windows once** - use PortMon/API Monitor to capture I/O if LED software exists

## Files Downloaded

- `/tmp/CYX_RGB_LED_Tool.zip` - LED control tool for different hardware
- `/tmp/CYX_RGB_LED_Tool/` - Extracted contents

## Safety Warnings

**NEVER write to I2C device 0x44** - crashes the system immediately.

**NEVER probe random I2C/EC registers without research** - can corrupt system state.

## References

- [OpenRGB](https://openrgb.org/) - Open source RGB control (doesn't support this hardware)
- [CYX_RGB_LED_Tool](https://drive.google.com/file/d/1Mg25zCwqapHI7qoxw_7rVSQVWh1gpQl9/view) - For AM08 Pro, not BOSGAME
- [T9Plus LED Control](https://www2.rigacci.org/wiki/doku.php/doc/appunti/hardware/t9plus_mini_pc_rgb_led_control) - Python script for different hardware
- [Mini PC Union Forum](https://minipcunion.com/) - Community for mini PC modding

## Tags

bosgame, ecolite, dnb10m, led, rgb, ring-light, it5570e, ec, embedded-controller, reverse-engineering, failed

## Incident Date

2026-01-24
