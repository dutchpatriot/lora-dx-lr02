# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python tools for DX-LR02 433MHz LoRa modules (ASR6601-based). These modules use a toggle-based AT command protocol and UART serial communication for wireless data transmission.

## Running Scripts

All scripts are standalone Python files. No build system - run directly:

```bash
python3 lora_receiver.py      # Simple receiver
python3 lora_sender.py        # Simple sender
python3 lora_chat.py          # Full-duplex CLI chat with usernames
python3 lora_gui.py           # Full-duplex tkinter GUI (chat + file transfer)
python3 lora_file_transfer.py send <file>   # Send file over LoRa
python3 lora_file_transfer.py receive       # Receive files over LoRa
python3 lora_config.py        # View module AT configuration
python3 lora_reset.py         # Reset module stuck in AT mode
```

Android/Termux:
```bash
termux-usb -e python lora_android.py /dev/bus/usb/001/002
termux-usb -e python lora_termux.py /dev/bus/usb/001/002
```

## Dependencies

- `pyserial` - Required for all scripts
- `tkinter` - Only for lora_gui.py (usually bundled with Python)
- `usb4a`/`usbserial4a` - Only for Android scripts

## Architecture

**AT Command Protocol:**
- Send `+++\r\n` to toggle between data mode and AT mode
- Response "Entry AT" = now in AT mode, "Exit AT" + "Power on" = now in data mode
- Same command toggles both directions

**Common Pattern (setup_module function):**
All scripts follow this pattern to ensure data mode:
1. Send `+++\r\n`, wait for response
2. If "Entry AT" received, send `+++\r\n` again to exit back to data mode
3. Module is now ready for transparent transmission

**Platform Abstraction:**
- Desktop: `serial.Serial` from pyserial
- Android (lora_android.py): `usb4a` + `usbserial4a`
- Termux (lora_termux.py): `termios` + `os.read`/`os.write` on file descriptors

**Full-Duplex Scripts (lora_chat.py, lora_gui.py):**
- Background thread for receiving messages
- Main thread handles user input/GUI
- lora_gui.py uses `queue.Queue` for thread-safe message passing to tkinter

**File Transfer Protocol (lora_file_transfer.py, lora_gui.py):**
- Stop-and-wait ARQ with ACK/NACK and retries
- Text-based packets for debugging compatibility
- Base64 encoding for binary-safe transmission
- CRC16-CCITT checksums on chunks and full file
- Protocol: `FILE:name:chunks:size` → `DATA:seq:crc:base64` → `DONE:crc`
- 100-byte chunks (conservative for SF12), 15s ACK timeout, 5 retries
- Received files saved to `./lora_received/`

## Hardware Defaults

Both modules must match these settings to communicate:
- Baud: 9600
- Frequency: 433 MHz
- Spreading Factor: 12
- MAC: ff,ff (broadcast)
- Mode: 0 (transparent transmission)

## Troubleshooting Commands

```bash
# Port permission issues
sudo usermod -a -G dialout $USER

# Port locked by crashed process
sudo fuser -k /dev/ttyUSB0
```

## SDR Listener Support

For passive reception with RTL-SDR dongles, see `SDR_LISTENER_GUIDE.md`. Uses gr-lora (GNU Radio) to decode transmissions from DX-LR02 modules - useful for emergency broadcast scenarios with many listeners.
