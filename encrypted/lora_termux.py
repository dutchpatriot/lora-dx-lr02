#!/usr/bin/env python3
"""
LoRa Encrypted for Termux using termux-usb file descriptor.
Uses AES-256-GCM encryption with pre-shared key.

Usage:
    termux-usb -r /dev/bus/usb/001/002
    termux-usb -e python lora_termux.py /dev/bus/usb/001/002
"""

import sys
import os
import time
import fcntl
import struct
import threading
import crypto_utils

# USB CDC constants
TIOCMGET = 0x5415
TIOCMSET = 0x5418
TIOCEXCL = 0x540C


def setup_serial(fd, baud=9600):
    """Configure the file descriptor for serial communication."""
    import termios

    # Get current settings
    attrs = termios.tcgetattr(fd)

    # Set baud rate
    baud_map = {
        9600: termios.B9600,
        19200: termios.B19200,
        38400: termios.B38400,
        57600: termios.B57600,
        115200: termios.B115200,
    }
    speed = baud_map.get(baud, termios.B9600)

    # Configure for raw mode
    attrs[0] = 0  # iflag
    attrs[1] = 0  # oflag
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag
    attrs[3] = 0  # lflag
    attrs[4] = speed  # ispeed
    attrs[5] = speed  # ospeed

    # Set VMIN and VTIME for non-blocking reads
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1  # 0.1 second timeout

    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def setup_module(fd):
    """Ensure module is in data mode."""
    # Flush any pending data
    try:
        os.read(fd, 1000)
    except:
        pass

    # Send +++ to toggle mode
    os.write(fd, b'+++\r\n')
    time.sleep(0.5)

    try:
        response = os.read(fd, 100).decode(errors='ignore')
    except:
        response = ""

    if 'Entry AT' in response:
        # Exit AT mode
        os.write(fd, b'+++\r\n')
        time.sleep(0.5)
        try:
            os.read(fd, 100)
        except:
            pass
        print("[*] Module set to data mode")
    elif 'Exit AT' in response:
        print("[*] Module now in data mode")
    else:
        print("[*] Module ready")


def receive_loop(fd, running, key):
    """Background receive thread."""
    buffer = ""
    while running[0]:
        try:
            data = os.read(fd, 256)
            if data:
                buffer += data.decode('utf-8', errors='ignore')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line and line != 'Power on':
                        timestamp = time.strftime('%H:%M:%S')

                        if crypto_utils.is_encrypted(line):
                            decrypted = crypto_utils.decrypt(line, key)
                            if decrypted:
                                print(f"\r[{timestamp}] \U0001F512 {decrypted}")
                            else:
                                print(f"\r[{timestamp}] \U0001F510 [Decryption failed]")
                        else:
                            print(f"\r[{timestamp}] \U000026A0 [UNENCRYPTED] {line}")

                        print("Send> ", end='', flush=True)
        except BlockingIOError:
            pass
        except Exception as e:
            if running[0]:
                print(f"\r[!] RX error: {e}")
        time.sleep(0.1)


def main():
    # Check crypto library
    if not crypto_utils.check_crypto_available():
        sys.exit(1)

    print("=" * 50)
    print("  LoRa Encrypted Transceiver (Termux)")
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
    print("[*] Encryption key loaded")

    # Get file descriptor from termux-usb
    # It's passed as an environment variable
    fd_str = os.environ.get('TERMUX_USB_FD')

    if fd_str:
        fd = int(fd_str)
        print(f"[*] Using termux-usb fd: {fd}")
    else:
        # Try opening directly (might work on some devices)
        if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
            fd = os.open(sys.argv[1], os.O_RDWR | os.O_NONBLOCK)
            print(f"[*] Opened {sys.argv[1]}")
        else:
            print("[!] No USB device available")
            print("Usage: termux-usb -e python lora_termux.py /dev/bus/usb/001/002")
            sys.exit(1)

    try:
        setup_serial(fd)
        time.sleep(1)
        setup_module(fd)

        print("[*] Ready! Type messages and press Enter.")
        print("[*] All messages are encrypted.")
        print("[*] Press Ctrl+C to exit.\n")

        running = [True]
        rx_thread = threading.Thread(target=receive_loop, args=(fd, running, key), daemon=True)
        rx_thread.start()

        while True:
            try:
                msg = input("Send> ")
                if msg:
                    encrypted = crypto_utils.encrypt(msg, key)
                    os.write(fd, (encrypted + '\r\n').encode('utf-8'))
                    timestamp = time.strftime('%H:%M:%S')
                    print(f"[{timestamp}] \U0001F512 {msg}")
            except EOFError:
                break

    except KeyboardInterrupt:
        print("\n[*] Exiting...")
    finally:
        running[0] = False
        try:
            os.close(fd)
        except:
            pass


if __name__ == '__main__':
    main()
