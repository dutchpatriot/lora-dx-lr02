#!/usr/bin/env python3
"""
LoRa Encrypted Sender for DX-LR02 module
Sends encrypted messages over LoRa using AES-256-GCM.
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
    ser.write(b'+++\r\n')
    time.sleep(0.5)
    response = ser.read(ser.in_waiting or 100).decode(errors='ignore')

    if 'Entry AT' in response:
        # We entered AT mode, exit it
        ser.write(b'+++\r\n')
        time.sleep(0.5)
        ser.read(ser.in_waiting or 100)
        print("[*] Module set to data mode")
    elif 'Exit AT' in response:
        print("[*] Module in data mode")
    else:
        print("[*] Module ready")

    ser.reset_input_buffer()


def send_message(ser, message, key):
    """Encrypt and send a message over LoRa"""
    encrypted = crypto_utils.encrypt(message, key)
    ser.write((encrypted + '\r\n').encode('utf-8'))
    print(f"[*] Sent (encrypted): {message}")
    print(f"    Ciphertext: {encrypted[:50]}...")


def main():
    # Check crypto library
    if not crypto_utils.check_crypto_available():
        sys.exit(1)

    print("=" * 50)
    print("  LoRa Encrypted Sender")
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

    print(f"[*] Using {PORT}")
    print("[*] Type messages to send. Press Ctrl+C to exit.\n")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(1)
        setup_module(ser)

        # Interactive mode
        while True:
            try:
                message = input("Message> ")
                if message:
                    send_message(ser, message, key)
                    time.sleep(0.5)
                    # Check for any response
                    if ser.in_waiting:
                        resp = ser.read(ser.in_waiting).decode(errors='ignore').strip()
                        if resp:
                            print(f"[*] Response: {resp}")
            except EOFError:
                break

    except serial.SerialException as e:
        print(f"[!] Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[*] Exiting...")
        ser.close()


if __name__ == '__main__':
    main()
