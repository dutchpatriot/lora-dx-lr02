#!/usr/bin/env python3
"""
LoRa Encrypted Receiver for DX-LR02 module
Listens for incoming LoRa messages and decrypts them.
Uses AES-256-GCM with pre-shared key.
"""

import serial
import time
import sys
import crypto_utils

# Configuration - adjust port as needed
PORT = '/dev/ttyUSB0'  # Linux - change if different
BAUD = 9600


def setup_module(ser):
    """Ensure module is in data mode (not AT mode)"""
    ser.reset_input_buffer()

    # Send +++ to check/toggle mode
    ser.write(b'+++\r\n')
    time.sleep(0.5)
    response = ser.read(ser.in_waiting or 100).decode(errors='ignore')

    if 'Entry AT' in response:
        # We just entered AT mode, exit it
        ser.write(b'+++\r\n')
        time.sleep(0.5)
        ser.read(ser.in_waiting or 100)
        print("[*] Module set to data mode")
    elif 'Exit AT' in response:
        # We were in AT mode, now in data mode
        print("[*] Module was in AT mode, now in data mode")
    else:
        # Unknown state, try sending +++ again to be safe
        time.sleep(0.3)
        ser.write(b'+++\r\n')
        time.sleep(0.5)
        resp2 = ser.read(ser.in_waiting or 100).decode(errors='ignore')
        if 'Entry AT' in resp2:
            ser.write(b'+++\r\n')
            time.sleep(0.5)
            ser.read(ser.in_waiting or 100)
        print("[*] Module initialized")

    ser.reset_input_buffer()


def main():
    # Check crypto library
    if not crypto_utils.check_crypto_available():
        sys.exit(1)

    print("=" * 50)
    print("  LoRa Encrypted Receiver")
    print("  AES-256-GCM + Pre-shared Key")
    print("=" * 50)

    # Handle key commands
    if len(sys.argv) > 2 and sys.argv[1] == '--set-key':
        try:
            crypto_utils.set_key_from_hex(sys.argv[2])
        except ValueError as e:
            print(f"[!] Invalid key: {e}")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == '--show-key':
        key = crypto_utils.get_or_create_key()
        print(f"[*] Current key: {crypto_utils.key_to_hex(key)}")
        sys.exit(0)

    # Load encryption key
    key = crypto_utils.get_or_create_key()
    print(f"[*] Encryption key loaded")

    print(f"[*] Listening on {PORT}")
    print("[*] Press Ctrl+C to exit\n")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(1)
        setup_module(ser)

        print("[*] Waiting for messages...\n")

        buffer = ""
        while True:
            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                try:
                    buffer += data.decode('utf-8', errors='ignore')

                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()

                        if line and line != 'Power on':
                            timestamp = time.strftime('%H:%M:%S')

                            if crypto_utils.is_encrypted(line):
                                decrypted = crypto_utils.decrypt(line, key)
                                if decrypted:
                                    print(f"[{timestamp}] \U0001F512 Decrypted: {decrypted}")
                                else:
                                    print(f"[{timestamp}] \U0001F510 [Decryption failed - wrong key?]")
                                    print(f"           Raw: {line[:60]}...")
                            else:
                                print(f"[{timestamp}] \U000026A0 [UNENCRYPTED]: {line}")
                except Exception as e:
                    print(f"[!] Error: {e}")
                    print(f"    Raw data: {data.hex()}")

            time.sleep(0.1)

    except serial.SerialException as e:
        print(f"[!] Error: {e}")
        print("[!] Make sure the correct port is specified and you have permissions.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[*] Exiting...")
        ser.close()


if __name__ == '__main__':
    main()
