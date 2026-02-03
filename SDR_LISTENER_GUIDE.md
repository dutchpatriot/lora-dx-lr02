# SDR Listener Guide for DX-LR02 LoRa Reception

Receive LoRa transmissions from DX-LR02 modules using an RTL-SDR dongle and gr-lora.

## Use Case

Emergency broadcast setup:
- **Transmitters**: DX-LR02 LoRa modules (your existing hardware)
- **Receivers**: Cheap RTL-SDR dongles with gr-lora software
- **Advantage**: One-to-many broadcast - unlimited passive listeners

## Hardware Requirements

| Component | Cost | Notes |
|-----------|------|-------|
| RTL-SDR dongle | ~$25-35 | RTL-SDR Blog V3/V4 recommended for better stability |
| 433 MHz antenna | ~$5-15 | Comes with most RTL-SDR kits, or use telescopic antenna tuned to ~17cm |
| USB extension cable | Optional | Reduces interference from computer |

Recommended: [RTL-SDR Blog V3](https://www.rtl-sdr.com/buy-rtl-sdr-dvb-t-dongles/) - has TCXO for better frequency stability.

## DX-LR02 Parameters to Match

Your modules use these settings (from `lora_config.py`):

| Parameter | Value | gr-lora setting |
|-----------|-------|-----------------|
| Frequency | 433 MHz | 433e6 |
| Spreading Factor | 12 | sf=12 |
| Bandwidth | 125 kHz | bw=125000 |
| Coding Rate | 4/6 (CR=2) | cr=2 |
| Preamble | 8 | preamble=8 |
| Sync Word | 0x12 (default) | sync_word=0x12 |

## Installation Options

### Option 1: Docker (Easiest - Recommended)

```bash
# Install Docker if not present
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in

# Pull gr-lora container
docker pull rpp0/gr-lora

# Run with RTL-SDR access
docker run -it --privileged -v /dev/bus/usb:/dev/bus/usb rpp0/gr-lora
```

### Option 2: Conda Environment (gr-lora_sdr from EPFL)

```bash
# Install Miniconda if not present
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh

# Create environment with gr-lora_sdr
conda create -n lora python=3.10
conda activate lora
conda install -c tapparelj -c conda-forge gnuradio-lora_sdr

# Install RTL-SDR support
conda install -c conda-forge gnuradio-osmosdr
```

### Option 3: Manual Installation (Ubuntu/Debian)

```bash
# Install GNU Radio 3.10
sudo apt update
sudo apt install gnuradio gnuradio-dev

# Install RTL-SDR support
sudo apt install rtl-sdr librtlsdr-dev gr-osmosdr

# Install gr-lora from source
git clone https://github.com/rpp0/gr-lora.git
cd gr-lora
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
sudo ldconfig
```

### Raspberry Pi Notes

```bash
# Same as Ubuntu, but use armhf packages
sudo apt install gnuradio gr-osmosdr rtl-sdr

# gr-lora compilation may take longer on Pi
# Consider using a Pi 4 with 4GB+ RAM
```

## RTL-SDR Setup

### 1. Blacklist Default DVB-T Drivers

```bash
# Create blacklist file
sudo tee /etc/modprobe.d/blacklist-rtlsdr.conf << 'EOF'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
EOF

# Reload
sudo modprobe -r dvb_usb_rtl28xxu rtl2832 rtl2830 2>/dev/null
```

### 2. Set USB Permissions

```bash
# Add udev rule for RTL-SDR
sudo tee /etc/udev/rules.d/20-rtlsdr.rules << 'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE:="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", MODE:="0666"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 3. Test RTL-SDR

```bash
# Should show your device
rtl_test -t

# Quick spectrum test at 433 MHz
rtl_fm -f 433000000 -s 1000000 - | aplay -r 1000000 -f S16_LE
# (Will sound like static, but confirms device works)
```

## GNU Radio Flowgraph for DX-LR02

Create this flowgraph in GNU Radio Companion (`gnuradio-companion`):

### Blocks to Add:

1. **RTL-SDR Source** (from osmocom)
   - Sample Rate: `1e6` (1 Msps)
   - Center Frequency: `433e6`
   - RF Gain: `40` (adjust based on signal strength)
   - IF Gain: `20`
   - BB Gain: `20`

2. **LoRa Receiver** (from gr-lora)
   - Spreading Factor: `12`
   - Sample Rate: `1e6`
   - Capture Frequency: `433e6`
   - Channel List: `[433e6]`
   - Bandwidth: `125000`

3. **Message Debug** (for console output)
   - Connect to LoRa Receiver output

4. **QT GUI Frequency Sink** (optional, for visualization)
   - Connect to RTL-SDR Source output

### Save and Run

Save as `lora_receiver.grc` and run with F6 or:

```bash
python3 lora_receiver.py
```

## Minimal Python Script

If you prefer scripting over GNU Radio Companion:

```python
#!/usr/bin/env python3
"""
SDR LoRa Receiver for DX-LR02 modules
Requires: gr-lora, gr-osmosdr
"""

from gnuradio import gr, blocks
import osmosdr
import lora

class LoraSDRReceiver(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "DX-LR02 SDR Receiver")

        # Parameters matching DX-LR02 defaults
        frequency = 433e6      # 433 MHz
        sample_rate = 1e6      # 1 Msps
        spreading_factor = 12  # SF12
        bandwidth = 125000     # 125 kHz

        # RTL-SDR Source
        self.rtlsdr = osmosdr.source(args="numchan=1")
        self.rtlsdr.set_sample_rate(sample_rate)
        self.rtlsdr.set_center_freq(frequency, 0)
        self.rtlsdr.set_gain_mode(False, 0)
        self.rtlsdr.set_gain(40, 0)
        self.rtlsdr.set_if_gain(20, 0)
        self.rtlsdr.set_bb_gain(20, 0)

        # LoRa Receiver
        self.lora_receiver = lora.lora_receiver(
            sample_rate,
            frequency,
            [frequency],  # channel list
            bandwidth,
            spreading_factor,
            False,  # implicit header
            4,      # coding rate
            True,   # crc
            False,  # reduced rate
            False   # disable drift correction
        )

        # Message output
        self.msg_debug = blocks.message_debug()

        # Connections
        self.connect(self.rtlsdr, self.lora_receiver)
        self.msg_connect(self.lora_receiver, "frames", self.msg_debug, "print")

if __name__ == "__main__":
    print("Starting DX-LR02 SDR Receiver...")
    print("Frequency: 433 MHz | SF: 12 | BW: 125 kHz")
    print("Press Ctrl+C to stop\n")

    try:
        tb = LoraSDRReceiver()
        tb.start()
        tb.wait()
    except KeyboardInterrupt:
        print("\nStopping...")
```

## Testing Your Setup

### 1. Verify Signal Reception

First, check you can see LoRa transmissions in the spectrum:

```bash
# Start GQRX or similar SDR software
gqrx
# Tune to 433 MHz, look for brief signal spikes when transmitting
```

### 2. Send Test Message

On your DX-LR02 transmitter:
```bash
python3 lora_sender.py
# Type: TEST123
```

### 3. Check SDR Output

The gr-lora receiver should print decoded payload to console.

## Frequency Offset Calibration

Cheap RTL-SDRs drift. If decoding fails:

### Method 1: Measure Offset with kalibrate-rtl

```bash
sudo apt install kalibrate-rtl
kal -s GSM900  # Scan for GSM signals
kal -c <channel>  # Measure offset
# Apply offset to center frequency
```

### Method 2: Visual Adjustment

1. Open GNU Radio flowgraph with FFT display
2. Transmit from DX-LR02
3. Note where signal appears vs. 433 MHz center
4. Adjust `capture_freq` variable by observed offset

gr-lora auto-corrects offsets up to ±15 kHz.

## Output to Network (for Multiple Listeners)

Add UDP output to share decoded messages:

```python
# In GNU Radio, add Message Socket Sink
# Host: 0.0.0.0
# Port: 40868

# Listeners can receive with:
nc -lu 40868
```

Or pipe to your own application for display/logging.

## Troubleshooting

### "No device found"
```bash
# Check USB connection
lsusb | grep -i rtl
# Should show: Realtek Semiconductor Corp. RTL2838

# Check permissions
ls -la /dev/bus/usb/*/*
```

### "Device or resource busy"
```bash
# Kill other SDR processes
sudo pkill -f rtl_
sudo pkill -f gqrx
```

### No Messages Decoded
1. **Check frequency**: Use GQRX to verify you see the signal
2. **Check SF**: Must be 12 for DX-LR02 defaults
3. **Check bandwidth**: Must be 125 kHz
4. **Increase gain**: Try RF gain 49 (max for RTL-SDR)
5. **Check antenna**: Ensure 433 MHz antenna is connected

### Garbled/Partial Messages
- Likely frequency offset - run calibration
- Or weak signal - improve antenna/reduce distance for testing

## Alternative: SDRangel (GUI-based)

If GNU Radio is too complex for some listeners:

```bash
# Install SDRangel
sudo apt install sdrangel

# Or AppImage from:
# https://github.com/f4exb/sdrangel/releases
```

SDRangel has a built-in LoRa demodulator plugin with GUI controls.

## Links

- [gr-lora (rpp0)](https://github.com/rpp0/gr-lora) - GNU Radio LoRa receiver
- [gr-lora_sdr (EPFL)](https://github.com/tapparelj/gr-lora_sdr) - Full transceiver implementation
- [RTL-SDR Blog](https://www.rtl-sdr.com/tag/lora/) - LoRa SDR articles
- [SDRangel](https://github.com/f4exb/sdrangel) - GUI SDR application

## License

MIT License - Same as main project.
