#!/usr/bin/env python3
"""
LoRa Configuration Viewer for DX-LR02 module
Shows current module settings.
"""

import serial
import time
import sys

# Configuration - adjust port as needed
PORT = '/dev/ttyUSB0'  # Linux - change if different
BAUD = 9600

def send_cmd(ser, cmd):
    ser.write((cmd + '\r\n').encode())
    time.sleep(0.5)
    return ser.read(ser.in_waiting or 500).decode(errors='ignore').strip()

def main():
    print(f"LoRa Config - Reading from {PORT}\n")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=2)
        time.sleep(1)
        ser.reset_input_buffer()

        # Enter AT mode
        resp = send_cmd(ser, '+++')
        if 'Exit' in resp or 'Power' in resp:
            time.sleep(0.3)
            resp = send_cmd(ser, '+++')

        if 'Entry AT' not in resp:
            print(f"Failed to enter AT mode: {resp}")
            sys.exit(1)

        print("=== Module Configuration ===\n")

        # Get full config
        resp = send_cmd(ser, 'AT+HELP')
        print(resp)

        # Get individual settings
        print("\n=== Individual Queries ===")
        for cmd in ['AT+MAC', 'AT+MODE', 'AT+LEVEL', 'AT+BAUD', 'AT+SLEEP']:
            resp = send_cmd(ser, cmd)
            print(f"{cmd}: {resp}")

        # Exit AT mode
        send_cmd(ser, '+++')
        ser.close()

    except serial.SerialException as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
