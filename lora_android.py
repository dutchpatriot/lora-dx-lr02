#!/usr/bin/env python3
"""
LoRa Transceiver for Android (Termux)
Works with USB serial devices via termux-usb.

Usage:
    termux-usb -r /dev/bus/usb/001/002   # First, grant permission
    termux-usb -e ./lora_android.py /dev/bus/usb/001/002
"""

import sys
import time
import threading

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
        print(f"[*] Module ready")

    ser.reset_input_buffer()

def receive_loop(ser, running):
    """Background thread to receive messages."""
    while running[0]:
        try:
            if hasattr(ser, 'in_waiting'):
                count = ser.in_waiting
            else:
                count = 1

            if count:
                data = ser.read(count)
                if data:
                    msg = data.decode('utf-8', errors='ignore').strip()
                    if msg and msg != 'Power on':
                        timestamp = time.strftime('%H:%M:%S')
                        print(f"\r[{timestamp}] < {msg}")
                        print("Send> ", end='', flush=True)
        except Exception as e:
            if running[0]:
                print(f"\r[!] RX Error: {e}")
        time.sleep(0.1)

def main():
    print("=" * 40)
    print("  LoRa Transceiver (Android/Termux)")
    print("=" * 40)

    try:
        print("[*] Connecting to LoRa module...")
        ser = get_serial_port()
        time.sleep(1)
        setup_module(ser)

        print("[*] Ready! Type messages and press Enter.")
        print("[*] Press Ctrl+C to exit.\n")

        # Start receive thread
        running = [True]
        rx_thread = threading.Thread(target=receive_loop, args=(ser, running), daemon=True)
        rx_thread.start()

        # Main send loop
        while True:
            try:
                msg = input("Send> ")
                if msg:
                    ser.write((msg + '\r\n').encode('utf-8'))
                    timestamp = time.strftime('%H:%M:%S')
                    print(f"[{timestamp}] > {msg}")
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
