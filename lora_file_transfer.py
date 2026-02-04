#!/usr/bin/env python3
"""
LoRa File Transfer - Send and receive files over LoRa with ACK/retry protocol.

Protocol:
  FILE:<filename>:<total_chunks>:<file_size>  - Initiate transfer
  DATA:<seq>:<crc16>:<base64_chunk>           - Data chunk
  ACK:<seq>                                    - Acknowledgment
  NACK:<seq>                                   - Request retransmit
  DONE:<crc16>                                 - Transfer complete
  OK                                           - Final confirmation
  ABORT                                        - Cancel transfer

Usage:
  python3 lora_file_transfer.py send <filepath>
  python3 lora_file_transfer.py receive
"""

import serial
import time
import sys
import os
import base64
import signal
import threading

PORT = '/dev/ttyUSB0'
BAUD = 9600

CHUNK_SIZE = 150      # Bytes of raw data per chunk
MAX_RETRIES = 5       # Retries per chunk
ACK_TIMEOUT = 10      # Seconds to wait for ACK (long for SF12)
RECEIVE_DIR = './lora_received'

ser = None
running = True


def cleanup(signum=None, frame=None):
    """Clean exit."""
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


def calculate_crc16(data):
    """Calculate CRC16-CCITT checksum."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return format(crc, '04x')


def send_packet(packet):
    """Send a packet over serial."""
    ser.write((packet + '\r\n').encode('utf-8'))
    time.sleep(0.1)  # Small delay for LoRa transmission


def read_line(timeout=ACK_TIMEOUT):
    """Read a line from serial with timeout."""
    buffer = ""
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            buffer += data.decode('utf-8', errors='ignore')
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if line and line != 'Power on':
                    return line
        time.sleep(0.05)
    return None


def wait_for_ack(expected_seq, timeout=ACK_TIMEOUT):
    """Wait for ACK with specific sequence number. Returns True if received."""
    line = read_line(timeout)
    if line is None:
        return False, "timeout"
    if line == f"ACK:{expected_seq}":
        return True, "ack"
    if line == f"NACK:{expected_seq}":
        return False, "nack"
    if line == "ABORT":
        return False, "abort"
    return False, f"unexpected: {line}"


def send_file(filepath):
    """Send a file over LoRa."""
    if not os.path.exists(filepath):
        print(f"[!] File not found: {filepath}")
        return False

    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)

    with open(filepath, 'rb') as f:
        data = f.read()

    file_crc = calculate_crc16(data)
    chunks = [data[i:i+CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]
    total_chunks = len(chunks)

    print(f"[*] Sending: {filename} ({filesize} bytes, {total_chunks} chunks)")
    print(f"[*] File CRC: {file_crc}")

    # Send FILE header
    header = f"FILE:{filename}:{total_chunks}:{filesize}"
    print(f"[>] {header}")

    for retry in range(MAX_RETRIES):
        send_packet(header)
        success, reason = wait_for_ack(0)
        if success:
            print(f"[<] ACK:0 - Receiver ready")
            break
        print(f"[!] No ACK for header (attempt {retry+1}/{MAX_RETRIES}): {reason}")
    else:
        print("[!] Failed to initiate transfer")
        return False

    # Send data chunks
    for seq, chunk in enumerate(chunks, 1):
        chunk_b64 = base64.b64encode(chunk).decode('ascii')
        chunk_crc = calculate_crc16(chunk)
        packet = f"DATA:{seq}:{chunk_crc}:{chunk_b64}"

        for retry in range(MAX_RETRIES):
            print(f"[>] DATA:{seq} ({len(chunk)} bytes, crc={chunk_crc})", end='')
            if retry > 0:
                print(f" [retry {retry}]", end='')
            print()

            send_packet(packet)
            success, reason = wait_for_ack(seq)

            if success:
                print(f"[<] ACK:{seq}")
                break
            print(f"[!] {reason}")
        else:
            print(f"[!] Failed to send chunk {seq} after {MAX_RETRIES} retries")
            send_packet("ABORT")
            return False

        # Progress
        progress = seq / total_chunks * 100
        print(f"[*] Progress: {progress:.1f}%")

    # Send DONE
    done_packet = f"DONE:{file_crc}"
    print(f"[>] {done_packet}")

    for retry in range(MAX_RETRIES):
        send_packet(done_packet)
        line = read_line()
        if line == "OK":
            print(f"[<] OK - Transfer complete!")
            return True
        print(f"[!] Waiting for OK (attempt {retry+1}/{MAX_RETRIES})")

    print("[!] Did not receive final OK")
    return False


def receive_file():
    """Receive a file over LoRa."""
    os.makedirs(RECEIVE_DIR, exist_ok=True)

    print(f"[*] Waiting for incoming file transfer...")
    print(f"[*] Files will be saved to: {RECEIVE_DIR}/")
    print("[*] Press Ctrl+C to cancel\n")

    # Wait for FILE header
    while running:
        line = read_line(timeout=1)
        if line is None:
            continue

        if line.startswith("FILE:"):
            parts = line.split(':')
            if len(parts) != 4:
                print(f"[!] Invalid FILE header: {line}")
                continue

            _, filename, total_chunks_str, filesize_str = parts
            try:
                total_chunks = int(total_chunks_str)
                filesize = int(filesize_str)
            except ValueError:
                print(f"[!] Invalid FILE header values: {line}")
                continue

            print(f"[<] {line}")
            print(f"[*] Receiving: {filename} ({filesize} bytes, {total_chunks} chunks)")

            # Send ACK for header
            send_packet("ACK:0")
            print(f"[>] ACK:0")

            # Receive chunks
            chunks = {}
            expected_seq = 1
            transfer_done = False

            while not transfer_done and running:
                line = read_line()
                if line is None:
                    print(f"[!] Timeout waiting for chunk {expected_seq}")
                    send_packet(f"NACK:{expected_seq}")
                    continue

                if line.startswith("DATA:"):
                    parts = line.split(':', 3)
                    if len(parts) != 4:
                        print(f"[!] Invalid DATA packet: {line[:50]}...")
                        continue

                    _, seq_str, claimed_crc, chunk_b64 = parts
                    try:
                        seq = int(seq_str)
                    except ValueError:
                        continue

                    print(f"[<] DATA:{seq} (crc={claimed_crc})")

                    # Decode and verify chunk
                    try:
                        chunk_data = base64.b64decode(chunk_b64)
                    except Exception as e:
                        print(f"[!] Base64 decode error: {e}")
                        send_packet(f"NACK:{seq}")
                        print(f"[>] NACK:{seq}")
                        continue

                    actual_crc = calculate_crc16(chunk_data)
                    if actual_crc != claimed_crc:
                        print(f"[!] CRC mismatch: expected {claimed_crc}, got {actual_crc}")
                        send_packet(f"NACK:{seq}")
                        print(f"[>] NACK:{seq}")
                        continue

                    # Store chunk
                    chunks[seq] = chunk_data
                    send_packet(f"ACK:{seq}")
                    print(f"[>] ACK:{seq}")

                    if seq == expected_seq:
                        expected_seq += 1
                        progress = len(chunks) / total_chunks * 100
                        print(f"[*] Progress: {progress:.1f}%")

                elif line.startswith("DONE:"):
                    claimed_file_crc = line.split(':')[1]
                    print(f"[<] {line}")

                    # Reassemble file
                    if len(chunks) != total_chunks:
                        print(f"[!] Missing chunks: got {len(chunks)}, expected {total_chunks}")
                        send_packet("ABORT")
                        break

                    file_data = b''.join(chunks[i] for i in range(1, total_chunks + 1))
                    actual_file_crc = calculate_crc16(file_data)

                    if actual_file_crc != claimed_file_crc:
                        print(f"[!] File CRC mismatch: expected {claimed_file_crc}, got {actual_file_crc}")
                        send_packet("ABORT")
                        break

                    # Save file
                    safe_filename = os.path.basename(filename)
                    output_path = os.path.join(RECEIVE_DIR, safe_filename)

                    # Avoid overwriting
                    if os.path.exists(output_path):
                        base, ext = os.path.splitext(safe_filename)
                        counter = 1
                        while os.path.exists(output_path):
                            output_path = os.path.join(RECEIVE_DIR, f"{base}_{counter}{ext}")
                            counter += 1

                    with open(output_path, 'wb') as f:
                        f.write(file_data)

                    print(f"[*] File saved: {output_path}")
                    print(f"[*] Size: {len(file_data)} bytes, CRC: {actual_file_crc}")
                    send_packet("OK")
                    print(f"[>] OK")
                    print("[*] Transfer complete!")
                    return True

                elif line == "ABORT":
                    print("[<] ABORT - Transfer cancelled by sender")
                    break

            print("[*] Waiting for next transfer...\n")


def main():
    global ser

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 lora_file_transfer.py send <filepath>")
        print("  python3 lora_file_transfer.py receive")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == 'send' and len(sys.argv) < 3:
        print("Usage: python3 lora_file_transfer.py send <filepath>")
        sys.exit(1)

    print("=" * 40)
    print("  LoRa File Transfer")
    print("=" * 40)

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

    if mode == 'send':
        filepath = sys.argv[2]
        success = send_file(filepath)
        sys.exit(0 if success else 1)
    elif mode == 'receive':
        receive_file()
    else:
        print(f"[!] Unknown mode: {mode}")
        print("Use 'send' or 'receive'")
        sys.exit(1)


if __name__ == '__main__':
    main()
