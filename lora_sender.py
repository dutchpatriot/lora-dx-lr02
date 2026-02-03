#!/usr/bin/env python3
"""
LoRa Sender for DX-LR02 module
Sends messages over LoRa.
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
        print("Module in data mode")

    ser.reset_input_buffer()

def send_message(ser, message):
    """Send a message over LoRa"""
    ser.write((message + '\r\n').encode('utf-8'))
    print(f"Sent: {message}")

def main():
    print(f"LoRa Sender - Using {PORT}")
    print("Type messages to send. Press Ctrl+C to exit.\n")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(1)
        setup_module(ser)

        # Interactive mode
        while True:
            try:
                message = input("Message> ")
                if message:
                    send_message(ser, message)
                    time.sleep(0.5)
                    # Check for any response
                    if ser.in_waiting:
                        resp = ser.read(ser.in_waiting).decode(errors='ignore').strip()
                        if resp:
                            print(f"Response: {resp}")
            except EOFError:
                break

    except serial.SerialException as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        ser.close()

if __name__ == '__main__':
    main()
