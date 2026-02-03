#!/usr/bin/env python3
"""
LoRa Encrypted Transceiver for Android (Termux)
Works with USB serial devices via termux-usb.
Uses AES-256-GCM encryption with pre-shared key.

Usage:
    termux-usb -r /dev/bus/usb/001/002   # First, grant permission
    termux-usb -e ./lora_android.py /dev/bus/usb/001/002
"""

import sys
import time
import threading
import crypto_utils

try:
    from usb4a import usb
    from usbserial4a import serial4a
    ANDROID = True
except ImportError:
    ANDROID = False
    import serial


def get_serial_port():
    """Get serial connection - Android or desktop."""
    if ANDROID:
        # Find CH341 device
        devices = usb.get_usb_device_list()
        for device in devices:
            if device.getVendorId() == 0x1a86:  # CH341 vendor ID
                return serial4a.get_serial_port(
                    device.getDeviceName(),
                    9600,
                    8,
                    'N',
                    1,
                    timeout=1
                )
        raise Exception("No CH341 device found")
    else:
        # Desktop fallback
        return serial.Serial('/dev/ttyUSB0', 9600, timeout=1)


def setup_module(ser):
    """Ensure module is in data mode."""
    ser.reset_input_buffer()
    ser.write(b'+++\r\n')
    time.sleep(0.5)

    response = b''
    if hasattr(ser, 'in_waiting'):
        response = ser.read(ser.in_waiting or 100)
    else:
        response = ser.read(100)

    response = response.decode(errors='ignore')

    if 'Entry AT' in response:
        ser.write(b'+++\r\n')
        time.sleep(0.5)
        ser.read(100)
        print("[*] Module set to data mode")
    elif 'Exit AT' in response:
        print("[*] Module now in data mode")
    else:
        print("[*] Module ready")

    ser.reset_input_buffer()


def receive_loop(ser, running, key):
    """Background thread to receive messages."""
    buffer = ""
    while running[0]:
        try:
            if hasattr(ser, 'in_waiting'):
                count = ser.in_waiting
            else:
                count = 1

            if count:
                data = ser.read(count)
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
        except Exception as e:
            if running[0]:
                print(f"\r[!] RX Error: {e}")
        time.sleep(0.1)


def main():
    # Check crypto library
    if not crypto_utils.check_crypto_available():
        sys.exit(1)

    print("=" * 50)
    print("  LoRa Encrypted Transceiver (Android/Termux)")
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

    try:
        print("[*] Connecting to LoRa module...")
        ser = get_serial_port()
        time.sleep(1)
        setup_module(ser)

        print("[*] Ready! Type messages and press Enter.")
        print("[*] All messages are encrypted.")
        print("[*] Press Ctrl+C to exit.\n")

        # Start receive thread
        running = [True]
        rx_thread = threading.Thread(target=receive_loop, args=(ser, running, key), daemon=True)
        rx_thread.start()

        # Main send loop
        while True:
            try:
                msg = input("Send> ")
                if msg:
                    encrypted = crypto_utils.encrypt(msg, key)
                    ser.write((encrypted + '\r\n').encode('utf-8'))
                    timestamp = time.strftime('%H:%M:%S')
                    print(f"[{timestamp}] \U0001F512 {msg}")
            except EOFError:
                break

    except KeyboardInterrupt:
        print("\n[*] Exiting...")
    except Exception as e:
        print(f"[!] Error: {e}")
        print("\nMake sure you ran:")
        print("  termux-usb -r /dev/bus/usb/001/002")
        print("  termux-usb -e ./lora_android.py /dev/bus/usb/001/002")
        sys.exit(1)
    finally:
        running[0] = False
        try:
            ser.close()
        except:
            pass


if __name__ == '__main__':
    main()
