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

### 9. CYX_RGB_LED_Tool Deep Reverse Engineering

Downloaded and extensively reverse-engineered the CYX_RGB_LED_Tool used by similar mini PCs (AM08 Pro).

**Key findings from radare2 disassembly:**

#### LED Mode Values Discovered
| Mode | Value | Icon Name | Effect |
|------|-------|-----------|--------|
| On/Static | 1 | 01_On | Solid LED |
| Auto/Rainbow | 2 | 06_Auto | Rainbow breathing (BOSGAME default!) |
| Breath | 3 | 03_Breath | Single color breathing |
| ColorLoop | 4 | 04_ColorLoop | Color cycling |

**Note:** Icon name 05_RainBow actually uses mode value 2 (same as Auto). There is no mode 5.

#### LED Write Protocol (fcn.0040a360)
The CYX tool writes to LED using this sequence:
```
Port = 0xC400 or 0x0400
1. Write 0x2E to port, Write 0x11 to port+1  (select reg 0x11)
2. Write 0x2F to port, Write high_byte to port+1  (color high byte)
3. Write 0x2E to port, Write 0x10 to port+1  (select reg 0x10)
4. Write 0x2F to port, Write low_byte to port+1  (color low byte)
5. Write 0x2E to port, Write 0x12 to port+1  (select reg 0x12)
6. Write 0x2F to port, Write mode to port+1  (mode value)
```

#### Key Code Locations
- Mode 2 (Rainbow) set at: 0x004093db (`mov eax, 2`)
- Mode 3 (Breath) set at: 0x00409025 (`mov eax, 3`)
- Mode 4 (ColorLoop) set at: 0x004091fb (`mov eax, 4`)
- Mode 1 (Static) set at: 0x00408e09 (direct write to [esi+0x1918])
- LED write function: 0x0040a360
- Port initialization: 0x0040a325 (`mov dword [esi], 0xc400`)

**Testing on BOSGAME:**
```bash
# Port 0x0400 responds (but is iTCO_wdt - watchdog timer)
# Port 0xC400 returns 0xFF (not mapped)
# SuperIO 0x4E responds with chip ID 0x5570 (IT5570E)
```

**Result:** CYX tool is built for IT5571 using ports 0xC400/0x0400. BOSGAME IT5570E uses different registers.

### 10. SuperIO Register Writes (IT5570E)

Attempted to write to IT5570E SuperIO registers using the CYX protocol:

```bash
# Enter SuperIO config mode
write 0x87 to port 0x4E (twice)

# Write via 0x2E/0x2F protocol
write 0x2E to 0x4E, write reg to 0x4F
write 0x2F to 0x4E, write value to 0x4F
```

**Tested writes:**
- Reg 0x10 = 0x00 (color low) - Write accepted, no LED change
- Reg 0x11 = 0x00 (color high) - Write accepted, no LED change
- Reg 0x12 = 0x01 (mode static) - Write accepted, no LED change

**Result:** Registers accept writes but don't control LED.

### 11. LDN Base Port Scan

Found LDN 0x10 with base address 0x0912:
```
LDN 0x10: Base=0x0912, Active=0x01
  Reg 0x60/0x61 = 0x0912 (first base)
  Reg 0x62/0x63 = 0x0910 (second base)
  Reg 0xF1 = 0x49 ('I')
  Reg 0xF2 = 0x4A ('J')
```

**Port scan 0x0910-0x0921:** All return 0xFF (not responding)

### 12. EC RAM Write Attempts

Wrote to EC registers via `/sys/kernel/debug/ec/ec0/io`:

| Register | Before | After | LED Effect |
|----------|--------|-------|------------|
| 0x80 | 0x02 | 0x01 | None |
| 0x80 | 0x01 | 0x00 | None |
| 0xA0 | 0x03 | 0x00 | None |

**Result:** EC accepts writes but LED doesn't respond. LED likely controlled via extended EC RAM (0x100+) or internal firmware.

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
3. **EC registers 0x00-0xFF** accept writes but don't control the LED
4. **SuperIO registers 0x10-0x12** accept writes but don't control the LED
5. **CYX_RGB_LED_Tool** is for IT5571, uses different ports (0xC400/0x0400)
6. **LED control is likely in:**
   - Extended EC RAM (0x100+ range, not accessible via standard EC interface)
   - EC firmware handling animation internally with no OS interface
   - Possibly only controllable via BIOS settings

## What We Learned

### CYX Tool LED Protocol (for IT5571, NOT IT5570E)
```
Mode values: 1=static, 2=rainbow, 3=breath, 4=colorloop
Ports: 0xC400 or 0x0400
Protocol: 0x2E/0x2F indirect register access
Registers: 0x10=color_low, 0x11=color_high, 0x12=mode
```

### IT5570E vs IT5571
- IT5570E chip ID: 0x5570 (confirmed via SuperIO 0x20/0x21)
- IT5571 uses ports 0xC400/0x0400 for LED
- IT5570E does NOT respond on these ports
- Different register layout or protocol

## Recommendations

1. **Check BIOS first** - Press DEL at boot to enter UEFI setup
   - Look in Advanced → Chipset or Peripherals for LED/RGB options
   - AMI Aptio BIOS may have hidden options (requires AMIBCP to unlock)
2. **Email BOSGAME support** - support@bosgamepc.com
   - Ask if LED control software exists for Linux
   - Ask if BIOS has hidden LED settings
3. **Check BOSGAME forum** - https://forum.bosgamepc.com/
4. **Boot Windows once** - use PortMon/API Monitor to capture I/O if BOSGAME releases LED software
5. **Accept the rainbow** - it looks fine, low power, no heat

## Files Downloaded

- `/tmp/CYX_RGB_LED_Tool.zip` - LED control tool for different hardware
- `/tmp/CYX_RGB_LED_Tool/` - Extracted contents

## Safety Warnings

**NEVER write to I2C device 0x44** - crashes the system immediately.

**NEVER probe random I2C/EC registers without research** - can corrupt system state.

## Scripts Created

- `scripts/bosgame/led-control-test.py` - Python script for testing LED control (didn't work but useful for future attempts)

## References

- [OpenRGB](https://openrgb.org/) - Open source RGB control (doesn't support this hardware)
- [CYX_RGB_LED_Tool](https://drive.google.com/file/d/1Mg25zCwqapHI7qoxw_7rVSQVWh1gpQl9/view) - For AM08 Pro IT5571, not BOSGAME IT5570E
- [T9Plus LED Control](https://www2.rigacci.org/wiki/doku.php/doc/appunti/hardware/t9plus_mini_pc_rgb_led_control) - Python script for different hardware
- [Mini PC Union Forum](https://minipcunion.com/) - Community for mini PC modding
- [BOSGAME BIOS Download](https://www.bosgamepc.com/pages/bios-download-center) - Official BIOS files
- [BOSGAME Support](https://www.bosgamepc.com/pages/support) - Driver downloads
- [BOSGAME Forum](https://forum.bosgamepc.com/) - Official community forum

## Tags

bosgame, ecolite, dnb10m, led, rgb, ring-light, it5570e, it5571, ec, embedded-controller, reverse-engineering, superio, cyx, failed

## Investigation Date

2026-01-24
