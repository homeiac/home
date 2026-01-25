#!/usr/bin/env python3
"""
BOSGAME Ecolite IT5570E LED Control Test Script

Based on reverse engineering of CYX_RGB_LED_Tool.exe

Protocol discovered:
- SuperIO chip IT5570E on ports 0x4E/0x4F
- LED registers: 0x10 (low byte), 0x11 (high byte), 0x12 (third param)
- Write sequence uses 0x2E/0x2F indirect access

Mode values:
- 1 = On (static)
- 2 = Auto (rainbow breathing) - BOSGAME default
- 3 = Breath (single color breathing)
- 4 = ColorLoop

WARNING: This script requires root and writes to hardware registers.
         Test on non-critical system first!
"""

import sys
import os
import argparse

def read_port(port):
    """Read a byte from I/O port"""
    with open('/dev/port', 'rb') as f:
        f.seek(port)
        return f.read(1)[0]

def write_port(port, value):
    """Write a byte to I/O port"""
    with open('/dev/port', 'wb') as f:
        f.seek(port)
        f.write(bytes([value & 0xFF]))

def superio_enter(base=0x4E):
    """Enter SuperIO config mode - write 0x87 twice"""
    write_port(base, 0x87)
    write_port(base, 0x87)

def superio_exit(base=0x4E):
    """Exit SuperIO config mode - write 0xAA"""
    write_port(base, 0xAA)

def superio_read(base, reg):
    """Read SuperIO register"""
    write_port(base, reg)
    return read_port(base + 1)

def superio_write(base, reg, value):
    """Write SuperIO register"""
    write_port(base, reg)
    write_port(base + 1, value)

def led_write_register(base, reg_num, value):
    """
    Write to LED register using CYX protocol:
    1. Write 0x2E to select index mode
    2. Write register number
    3. Write 0x2F to select data mode
    4. Write value
    """
    # Select index register
    write_port(base, 0x2E)
    write_port(base + 1, reg_num)
    # Select data register and write
    write_port(base, 0x2F)
    write_port(base + 1, value)

def led_read_register(base, reg_num):
    """Read LED register using CYX protocol"""
    write_port(base, 0x2E)
    write_port(base + 1, reg_num)
    write_port(base, 0x2F)
    return read_port(base + 1)

def check_chip_id(base=0x4E):
    """Check if IT5570E is present"""
    superio_enter(base)
    chip_id_high = superio_read(base, 0x20)
    chip_id_low = superio_read(base, 0x21)
    superio_exit(base)

    chip_id = (chip_id_high << 8) | chip_id_low
    return chip_id

def set_led_mode(mode, color_value=0x0000, base=0x4E):
    """
    Set LED mode

    mode: 1=static, 2=auto/rainbow, 3=breath, 4=colorloop
    color_value: 16-bit color value (for static/breath modes)
    """
    print(f"Setting LED mode to {mode} with color value 0x{color_value:04X}")

    # The CYX tool writes:
    # Register 0x11 = high byte of value (color_value >> 8) & 0xFF
    # Register 0x10 = low byte of value (color_value & 0xFF)
    # Register 0x12 = mode number

    high_byte = (color_value >> 8) & 0xFF
    low_byte = color_value & 0xFF

    print(f"  Writing reg 0x10 = 0x{low_byte:02X}")
    print(f"  Writing reg 0x11 = 0x{high_byte:02X}")
    print(f"  Writing reg 0x12 = 0x{mode:02X}")

    # Enter SuperIO config mode
    superio_enter(base)

    # Try writing via the CYX protocol
    led_write_register(base, 0x11, high_byte)
    led_write_register(base, 0x10, low_byte)
    led_write_register(base, 0x12, mode)

    superio_exit(base)
    print("Done!")

def read_led_status(base=0x4E):
    """Read current LED register values"""
    superio_enter(base)

    reg10 = led_read_register(base, 0x10)
    reg11 = led_read_register(base, 0x11)
    reg12 = led_read_register(base, 0x12)

    superio_exit(base)

    return reg10, reg11, reg12

def try_ldn_led(base=0x4E, ldn=0x10):
    """Try accessing LED via LDN (Logical Device Number)"""
    print(f"Trying LDN 0x{ldn:02X}...")

    superio_enter(base)

    # Select LDN
    superio_write(base, 0x07, ldn)

    # Read base address
    base_high = superio_read(base, 0x60)
    base_low = superio_read(base, 0x61)
    ldn_base = (base_high << 8) | base_low

    # Read activation status
    active = superio_read(base, 0x30)

    print(f"  LDN 0x{ldn:02X}: Base=0x{ldn_base:04X}, Active=0x{active:02X}")

    # Try reading some registers in this LDN
    for reg in [0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5]:
        val = superio_read(base, reg)
        if val != 0x00 and val != 0xFF:
            print(f"    Reg 0x{reg:02X} = 0x{val:02X}")

    superio_exit(base)
    return ldn_base, active

def main():
    parser = argparse.ArgumentParser(description='BOSGAME IT5570E LED Control Test')
    parser.add_argument('--check', action='store_true', help='Check chip ID only')
    parser.add_argument('--read', action='store_true', help='Read current LED status')
    parser.add_argument('--mode', type=int, choices=[0,1,2,3,4], help='Set LED mode (0=off?, 1=static, 2=auto, 3=breath, 4=colorloop)')
    parser.add_argument('--off', action='store_true', help='Try to turn LED off (mode 0)')
    parser.add_argument('--static', action='store_true', help='Set to static mode (mode 1)')
    parser.add_argument('--scan-ldn', action='store_true', help='Scan all LDNs')
    parser.add_argument('--base', type=lambda x: int(x, 0), default=0x4E, help='SuperIO base port (default 0x4E)')

    args = parser.parse_args()

    if os.geteuid() != 0:
        print("ERROR: This script requires root privileges")
        print("Run with: sudo python3 led-control-test.py")
        sys.exit(1)

    base = args.base

    # Always check chip ID first
    chip_id = check_chip_id(base)
    print(f"Chip ID: 0x{chip_id:04X}", end="")
    if chip_id == 0x5570:
        print(" (IT5570E confirmed!)")
    elif chip_id == 0x5571:
        print(" (IT5571 - CYX tool compatible)")
    else:
        print(" (Unknown chip)")

    if args.check:
        return

    if args.scan_ldn:
        print("\nScanning LDNs...")
        for ldn in range(0x20):
            try_ldn_led(base, ldn)
        return

    if args.read:
        print("\nReading LED registers...")
        reg10, reg11, reg12 = read_led_status(base)
        print(f"  Reg 0x10 = 0x{reg10:02X}")
        print(f"  Reg 0x11 = 0x{reg11:02X}")
        print(f"  Reg 0x12 = 0x{reg12:02X}")
        return

    if args.off:
        print("\nTrying to turn LED OFF (mode 0)...")
        set_led_mode(0, 0x0000, base)
        return

    if args.static:
        print("\nSetting LED to STATIC mode (mode 1)...")
        set_led_mode(1, 0x0000, base)
        return

    if args.mode is not None:
        print(f"\nSetting LED to mode {args.mode}...")
        set_led_mode(args.mode, 0x0000, base)
        return

    # Default: just show status
    print("\nUse --help to see available options")
    print("Examples:")
    print("  sudo python3 led-control-test.py --check      # Check chip ID")
    print("  sudo python3 led-control-test.py --read       # Read LED registers")
    print("  sudo python3 led-control-test.py --off        # Try to turn off")
    print("  sudo python3 led-control-test.py --static     # Set to static mode")
    print("  sudo python3 led-control-test.py --mode 2     # Set to auto/rainbow")

if __name__ == '__main__':
    main()
