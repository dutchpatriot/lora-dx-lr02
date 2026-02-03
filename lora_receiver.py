#!/usr/bin/env python3
"""
LoRa Receiver for DX-LR02 module
Listens for incoming LoRa messages and prints them.
"""

import serial
import time
import sys

# Configuration - adjust port as needed
PORT = '/dev/ttyUSB0'  # Linux - change if different
BAUD = 9600

def setup_module(ser):
    """Ensure module is in data mode (not AT mode)"""
    ser.reset_input_buffer()
    # Send +++ to toggle mode
    ser.write(b'+++\r\n')
    time.sleep(0.5)
    response = ser.read(ser.in_waiting or 100).decode(errors='ignore')

    if 'Entry AT' in response:
        # We entered AT mode, exit it
        ser.write(b'+++\r\n')
        time.sleep(0.5)
        ser.read(ser.in_waiting or 100)
        print("Module set to data mode")
    elif 'Exit AT' in response:
        print("Module already exiting to data mode")
    else:
        print(f"Module response: {response.strip()}")

    ser.reset_input_buffer()

def main():
    print(f"LoRa Receiver - Listening on {PORT}")
    print("Press Ctrl+C to exit\n")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(1)
        setup_module(ser)

        print("Waiting for messages...\n")

        while True:
            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                try:
                    message = data.decode('utf-8').strip()
                    if message and message != 'Power on':
                        timestamp = time.strftime('%H:%M:%S')
                        print(f"[{timestamp}] Received: {message}")
                except:
                    print(f"[RAW] Received: {data.hex()}")
            time.sleep(0.1)

    except serial.SerialException as e:
        print(f"Error: {e}")
        print("Make sure the correct port is specified and you have permissions.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        ser.close()

if __name__ == '__main__':
    main()
