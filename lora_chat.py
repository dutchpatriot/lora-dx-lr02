#!/usr/bin/env python3
"""
LoRa Chat - Combined send/receive for DX-LR02 module.
Single script that does both directions (full duplex).
"""

import serial
import time
import sys
import threading
import signal

PORT = '/dev/ttyUSB0'
BAUD = 9600

ser = None
running = True

def cleanup(signum=None, frame=None):
    """Clean exit - ensure module is in data mode."""
    global running
    running = False
    print("\n[*] Exiting...")
    if ser and ser.is_open:
        ser.close()
    sys.exit(0)

def setup_module():
    """Ensure module is in data mode."""
    ser.reset_input_buffer()
    ser.write(b'+++\r\n')
    time.sleep(0.5)
    response = ser.read(ser.in_waiting or 100).decode(errors='ignore')

    if 'Entry AT' in response:
        ser.write(b'+++\r\n')
        time.sleep(0.5)
        ser.read(ser.in_waiting or 100)
        print("[*] Module set to data mode")
    elif 'Exit AT' in response:
        print("[*] Module was in AT mode, now in data mode")
    else:
        print("[*] Module ready")

    ser.reset_input_buffer()

def receive_loop():
    """Background thread for receiving messages."""
    buffer = ""
    while running:
        try:
            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                buffer += data.decode('utf-8', errors='ignore')

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line and line != 'Power on':
                        timestamp = time.strftime('%H:%M:%S')
                        # Print on new line, then reshow prompt
                        print(f"\r[{timestamp}] < {line}          ")
                        print("You> ", end='', flush=True)
        except Exception as e:
            if running:
                print(f"\r[!] Error: {e}")
        time.sleep(0.05)

def main():
    global ser

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("=" * 40)
    print("  LoRa Chat (Full Duplex)")
    print("=" * 40)
    print(f"[*] Connecting to {PORT}...")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.1)
        time.sleep(1)
        setup_module()
    except serial.SerialException as e:
        print(f"[!] Cannot open {PORT}: {e}")
        print("[!] Is another script using the port?")
        print("[!] Try: sudo fuser -k /dev/ttyUSB0")
        sys.exit(1)

    print("[*] Ready! Type messages and press Enter.")
    print("[*] Press Ctrl+C to exit.\n")

    # Start receive thread
    rx_thread = threading.Thread(target=receive_loop, daemon=True)
    rx_thread.start()

    # Main loop - send messages
    while running:
        try:
            msg = input("You> ")
            if msg.strip():
                ser.write((msg + '\r\n').encode('utf-8'))
                timestamp = time.strftime('%H:%M:%S')
                print(f"[{timestamp}] > {msg}")
        except EOFError:
            break

    cleanup()

if __name__ == '__main__':
    main()
