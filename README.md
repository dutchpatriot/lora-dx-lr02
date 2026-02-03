# DX-LR02 LoRa Module - Python Tools

Python tools for the DX-Smart DX-LR02 433MHz LoRa modules (and compatible ASR6601-based modules).

These modules are sold under various names on Amazon/AliExpress but share the same firmware and AT command interface. This repository provides working code and documentation that's otherwise scattered across random listings and forums.

## Hardware

**Tested Module:** DX-LR02_433T22D (DX-Smart)

| Specification | Value |
|---------------|-------|
| Chip | ASR6601 SoC |
| Frequency | 433-475 MHz |
| Power | 22 dBm |
| Range | Up to 5km (line of sight) |
| Interface | UART (USB via CH341) |
| Voltage | 3.3V - 5.5V |

**Pinout:** M0, M1, UART_RX, UART_TX, AUX, VCC, GND

## Quick Start

### Requirements

```bash
pip install pyserial
# For GUI:
# tkinter is included with Python on most systems
# On Debian/Ubuntu: sudo apt install python3-tk
```

### Find Your Port

```bash
# Linux
ls /dev/ttyUSB*

# macOS
ls /dev/tty.usbserial*

# Windows: Check Device Manager for COM port
```

### Test Communication

1. Connect two modules to two computers
2. Run on first computer:
   ```bash
   python3 lora_receiver.py
   ```
3. Run on second computer:
   ```bash
   python3 lora_sender.py
   ```
4. Type a message and press Enter

### GUI Application (Full Duplex)

```bash
python3 lora_gui.py
```

## AT Command Reference

The DX-LR02 uses a toggle-based AT command mode.

### Entering/Exiting AT Mode

| Command | Response | Description |
|---------|----------|-------------|
| `+++\r\n` | `Entry AT` | Enter AT command mode |
| `+++\r\n` | `Exit AT` + `Power on` | Exit to data mode |

**Important:** The module toggles between modes. Send `+++\r\n` once to enter, again to exit.

### Query Commands (in AT mode)

| Command | Example Response | Description |
|---------|------------------|-------------|
| `AT` | `OK` | Test connection |
| `AT+HELP` | *(see below)* | Show all parameters |
| `AT+MAC` | `+MAC=ff,ff` | Get MAC address |
| `AT+MODE` | `+MODE=0` | Get operating mode |
| `AT+LEVEL` | `+LEVEL=0` | Get speed level |
| `AT+BAUD` | `+BAUD=4` | Get baud rate setting |
| `AT+SLEEP` | `+SLEEP=2` | Get sleep mode |

### AT+HELP Output Explained

```
LoRa Parameter:
+VERSION=V2.2.0          # Firmware version
MODE:0                   # 0=Transparent, 1=Fixed point
LEVEL:0 >> 244.140625bps # Speed level (0-7)
SLEEP:2                  # Sleep mode setting
Frequency:433000000hz    # Operating frequency
MAC:ff,ff                # Module address (ff,ff = broadcast)
Bandwidth:0              # LoRa bandwidth setting
Spreading Factor:12      # LoRa SF (higher = longer range, slower)
Coding rate:2            # Error correction level
CRC:0(false)             # CRC check disabled
Preamble:8               # Preamble length
IQ:0(false)              # IQ inversion disabled
Power:22dBm              # Transmit power
```

### Other Commands

| Command | Description |
|---------|-------------|
| `AT+DEFAULT` | Reset to factory defaults |

### Baud Rate Values

| Value | Baud Rate |
|-------|-----------|
| 0 | 1200 |
| 1 | 2400 |
| 2 | 4800 |
| 3 | 9600 |
| 4 | 9600 (default) |
| 5 | 19200 |
| 6 | 38400 |
| 7 | 57600 |
| 8 | 115200 |

## Operating Modes

### Mode 0: Transparent Transmission (Default)

In this mode, the module acts as a wireless serial bridge:
- Exit AT mode with `+++\r\n`
- Any data sent to UART is transmitted over LoRa
- Any data received over LoRa is output on UART
- All modules with MAC `ff,ff` receive all transmissions (broadcast)

### Mode 1: Fixed Point

Allows addressing specific modules by their MAC address.
Data format: `[target MAC high],[target MAC low],[data]`

## Default Settings

Both modules must have matching settings to communicate:

| Parameter | Default | Notes |
|-----------|---------|-------|
| Frequency | 433 MHz | Must match |
| MAC | ff,ff | Broadcast (receives everything) |
| Mode | 0 | Transparent |
| Baud | 9600 | Serial speed |
| SF | 12 | Spreading factor |
| Power | 22 dBm | Max power |

## Troubleshooting

### No response from module

1. Check the port: `ls /dev/ttyUSB*`
2. Check permissions: `sudo usermod -a -G dialout $USER` (logout/login required)
3. Try the default baud rate: 9600

### Modules not communicating

1. Run `python3 lora_config.py` on both - settings must match
2. Check frequency, spreading factor, and bandwidth are identical
3. Ensure both are in data mode (not AT mode)
4. Check antenna connections

### "Entry AT" keeps appearing in received data

The sender is still in AT mode. Send `+++\r\n` to exit to data mode.

### Module not responding / ERROR=102

The serial port may be held by a crashed process:
```bash
# Kill processes using the port
sudo fuser -k /dev/ttyUSB0

# Then reset the module
python3 lora_reset.py
```

## File Descriptions

| File | Description |
|------|-------------|
| `lora_gui.py` | Full-duplex GUI application |
| `lora_receiver.py` | CLI receiver script |
| `lora_sender.py` | CLI sender script |
| `lora_config.py` | View module configuration |
| `lora_reset.py` | Reset module if stuck in AT mode |

## Protocol Notes

- The module automatically handles LoRa modulation/demodulation
- No packet framing is provided - you receive raw bytes as sent
- For reliable communication, implement your own framing/checksums
- The `\r\n` line ending is recommended for text messages

## Links

- [DX-Smart Manufacturer](https://en.szdx-smart.com)
- [ASR6601 Datasheet](https://www.asr-semi.com/uploads/file/ASR6601_Datasheet_V1.0.pdf)

## License

MIT License - Use freely, attribution appreciated.
