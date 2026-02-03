#!/usr/bin/env python3
"""
LoRa for Termux using termux-usb file descriptor.

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

def receive_loop(fd, running):
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
                        print(f"\r[{timestamp}] < {line}")
                        print("Send> ", end='', flush=True)
        except BlockingIOError:
            pass
        except Exception as e:
            if running[0]:
                print(f"\r[!] RX error: {e}")
        time.sleep(0.1)

def main():
    print("=" * 40)
    print("  LoRa Transceiver (Termux)")
    print("=" * 40)

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
        print("[*] Press Ctrl+C to exit.\n")

        running = [True]
        rx_thread = threading.Thread(target=receive_loop, args=(fd, running), daemon=True)
        rx_thread.start()

        while True:
            try:
                msg = input("Send> ")
                if msg:
                    os.write(fd, (msg + '\r\n').encode('utf-8'))
                    timestamp = time.strftime('%H:%M:%S')
                    print(f"[{timestamp}] > {msg}")
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
