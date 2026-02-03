#!/usr/bin/env python3
"""
LoRa Encrypted Chat - Combined send/receive for DX-LR02 module.
Single script that does both directions (full duplex).
Uses AES-256-GCM encryption with pre-shared key.
"""

import serial
import time
import sys
import threading
import signal
import socket
import crypto_utils

PORT = '/dev/ttyUSB0'
BAUD = 9600

ser = None
running = True
username = None
encryption_key = None


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

                        # Try to decrypt
                        if crypto_utils.is_encrypted(line):
                            decrypted = crypto_utils.decrypt(line, encryption_key)
                            if decrypted:
                                print(f"\r[{timestamp}] \U0001F512 {decrypted}                    ")
                            else:
                                print(f"\r[{timestamp}] \U0001F510 [Decryption failed - wrong key?]")
                        else:
                            # Unencrypted message
                            print(f"\r[{timestamp}] \U000026A0 [UNENCRYPTED] {line}")

                        print(f"{username}> ", end='', flush=True)
        except Exception as e:
            if running:
                print(f"\r[!] Error: {e}")
        time.sleep(0.05)


def get_username():
    """Get username from user or generate from hostname."""
    default = socket.gethostname().split('.')[0][:10]

    print(f"Enter your name [{default}]: ", end='', flush=True)
    try:
        name = input().strip()
    except:
        name = ""

    return name if name else default


def main():
    global ser, username, encryption_key

    # Check crypto library
    if not crypto_utils.check_crypto_available():
        sys.exit(1)

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("=" * 50)
    print("  LoRa Encrypted Chat (Full Duplex)")
    print("  AES-256-GCM + Pre-shared Key")
    print("=" * 50)

    # Load or create encryption key
    encryption_key = crypto_utils.get_or_create_key()
    print(f"[*] Encryption key loaded")

    # Check for --set-key argument
    if len(sys.argv) > 2 and sys.argv[1] == '--set-key':
        try:
            encryption_key = crypto_utils.set_key_from_hex(sys.argv[2])
            print("[*] Restart the chat to use the new key.")
        except ValueError as e:
            print(f"[!] Invalid key: {e}")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == '--show-key':
        print(f"[*] Current key: {crypto_utils.key_to_hex(encryption_key)}")
        sys.exit(0)

    username = get_username()
    print(f"[*] Joining as: {username}")
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
    print("[*] All messages are encrypted end-to-end.")
    print("[*] Press Ctrl+C to exit.\n")

    # Start receive thread
    rx_thread = threading.Thread(target=receive_loop, daemon=True)
    rx_thread.start()

    # Announce joining (encrypted)
    join_msg = f"* {username} joined the chat"
    encrypted_join = crypto_utils.encrypt(join_msg, encryption_key)
    ser.write((encrypted_join + '\r\n').encode('utf-8'))

    # Main loop - send messages
    while running:
        try:
            msg = input(f"{username}> ")
            if msg.strip():
                # Format: "username: message"
                full_msg = f"{username}: {msg}"
                encrypted_msg = crypto_utils.encrypt(full_msg, encryption_key)
                ser.write((encrypted_msg + '\r\n').encode('utf-8'))
                timestamp = time.strftime('%H:%M:%S')
                print(f"[{timestamp}] \U0001F512 {full_msg}")
        except EOFError:
            break

    cleanup()


if __name__ == '__main__':
    main()
