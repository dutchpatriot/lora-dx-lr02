#!/usr/bin/env python3
"""
Reset DX-LR02 module to data mode.
Run this if the module gets stuck in AT mode.
"""

import serial
import time
import sys

PORT = '/dev/ttyUSB0'
BAUD = 9600

def main():
    print(f"Resetting module on {PORT}...")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=2)
        time.sleep(0.5)
        ser.reset_input_buffer()

        # Toggle twice to ensure we end up in data mode
        for i in range(2):
            ser.write(b'+++\r\n')
            time.sleep(0.5)
            resp = ser.read(ser.in_waiting or 100).decode(errors='ignore').strip()
            print(f"  Response {i+1}: {resp}")

            if 'Exit AT' in resp or 'Power on' in resp:
                print("\nModule is now in DATA mode (ready to send/receive)")
                break
            elif 'Entry AT' in resp:
                print("  (In AT mode, toggling out...)")

        ser.close()

    except serial.SerialException as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
