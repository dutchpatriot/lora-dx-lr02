#!/usr/bin/env python3
"""
LoRa Full-Duplex GUI Application for DX-LR02 modules.

A simple chat-like interface for bidirectional LoRa communication
with file transfer support.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import queue
import time
import os
import base64
from datetime import datetime

CHUNK_SIZE = 100      # Bytes per chunk (conservative for SF12)
MAX_RETRIES = 5       # Retries per chunk
ACK_TIMEOUT = 15      # Seconds to wait for ACK
RECEIVE_DIR = './lora_received'


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


class LoRaModule:
    """Handles serial communication with the DX-LR02 LoRa module."""

    def __init__(self, port, baud=9600):
        self.port = port
        self.baud = baud
        self.serial = None
        self.running = False
        self.rx_queue = queue.Queue()

        # File transfer state
        self.ft_mode = None  # 'send', 'receive', or None
        self.ft_queue = queue.Queue()  # For ACKs during send
        self.ft_progress_queue = queue.Queue()  # Progress updates for GUI
        self.ft_receiving = None  # Dict with receive state

    def connect(self):
        """Connect to the module and ensure it's in data mode."""
        self.serial = serial.Serial(self.port, self.baud, timeout=0.1)
        time.sleep(1)
        self.serial.reset_input_buffer()

        # Ensure we're in data mode
        self.serial.write(b'+++\r\n')
        time.sleep(0.5)
        response = self.serial.read(self.serial.in_waiting or 100).decode(errors='ignore')

        if 'Entry AT' in response:
            # We entered AT mode, exit it
            self.serial.write(b'+++\r\n')
            time.sleep(0.5)
            self.serial.read(self.serial.in_waiting or 100)

        self.serial.reset_input_buffer()
        self.running = True
        return True

    def disconnect(self):
        """Disconnect from the module."""
        self.running = False
        if self.serial and self.serial.is_open:
            self.serial.close()

    def send(self, message):
        """Send a message over LoRa."""
        if self.serial and self.serial.is_open:
            self.serial.write((message + '\r\n').encode('utf-8'))
            return True
        return False

    def receive_loop(self):
        """Background loop to receive messages."""
        buffer = ""
        while self.running:
            try:
                if self.serial and self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
                    buffer += data

                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line and line != 'Power on':
                            # Route to appropriate queue based on mode
                            if self.ft_mode == 'send' and line.startswith(('ACK:', 'NACK:', 'OK', 'ABORT')):
                                self.ft_queue.put(line)
                            elif line.startswith(('FILE:', 'DATA:', 'DONE:', 'ABORT')):
                                self._handle_incoming_transfer(line)
                            else:
                                self.rx_queue.put(line)
                time.sleep(0.05)
            except Exception as e:
                if self.running:
                    self.rx_queue.put(f"[ERROR] {e}")
                break

    def _handle_incoming_transfer(self, line):
        """Handle incoming file transfer packets."""
        if line.startswith('FILE:'):
            parts = line.split(':')
            if len(parts) == 4:
                _, filename, total_str, size_str = parts
                try:
                    total = int(total_str)
                    size = int(size_str)
                    self.ft_receiving = {
                        'filename': filename,
                        'total_chunks': total,
                        'size': size,
                        'chunks': {},
                        'expected_seq': 1
                    }
                    self.ft_mode = 'receive'
                    self.send('ACK:0')
                    self.ft_progress_queue.put(('start', filename, total, size))
                except ValueError:
                    pass

        elif line.startswith('DATA:') and self.ft_receiving:
            parts = line.split(':', 3)
            if len(parts) == 4:
                _, seq_str, claimed_crc, chunk_b64 = parts
                try:
                    seq = int(seq_str)
                    chunk_data = base64.b64decode(chunk_b64)
                    actual_crc = calculate_crc16(chunk_data)

                    if actual_crc == claimed_crc:
                        self.ft_receiving['chunks'][seq] = chunk_data
                        self.send(f'ACK:{seq}')
                        progress = len(self.ft_receiving['chunks']) / self.ft_receiving['total_chunks']
                        self.ft_progress_queue.put(('progress', progress, seq))
                    else:
                        self.send(f'NACK:{seq}')
                except Exception:
                    self.send(f'NACK:{seq_str}')

        elif line.startswith('DONE:') and self.ft_receiving:
            claimed_crc = line.split(':')[1]
            chunks = self.ft_receiving['chunks']
            total = self.ft_receiving['total_chunks']

            if len(chunks) == total:
                file_data = b''.join(chunks[i] for i in range(1, total + 1))
                actual_crc = calculate_crc16(file_data)

                if actual_crc == claimed_crc:
                    # Save file
                    os.makedirs(RECEIVE_DIR, exist_ok=True)
                    filename = os.path.basename(self.ft_receiving['filename'])
                    output_path = os.path.join(RECEIVE_DIR, filename)

                    if os.path.exists(output_path):
                        base, ext = os.path.splitext(filename)
                        counter = 1
                        while os.path.exists(output_path):
                            output_path = os.path.join(RECEIVE_DIR, f"{base}_{counter}{ext}")
                            counter += 1

                    with open(output_path, 'wb') as f:
                        f.write(file_data)

                    self.send('OK')
                    self.ft_progress_queue.put(('done', output_path, len(file_data)))
                else:
                    self.send('ABORT')
                    self.ft_progress_queue.put(('error', 'CRC mismatch'))
            else:
                self.send('ABORT')
                self.ft_progress_queue.put(('error', f'Missing chunks: {len(chunks)}/{total}'))

            self.ft_receiving = None
            self.ft_mode = None

        elif line == 'ABORT':
            self.ft_receiving = None
            self.ft_mode = None
            self.ft_progress_queue.put(('error', 'Transfer aborted by sender'))

    def _wait_for_ack(self, expected_seq, timeout=ACK_TIMEOUT):
        """Wait for ACK with timeout."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                line = self.ft_queue.get(timeout=0.1)
                if line == f'ACK:{expected_seq}':
                    return True, 'ack'
                if line == f'NACK:{expected_seq}':
                    return False, 'nack'
                if line == 'OK':
                    return True, 'ok'
                if line == 'ABORT':
                    return False, 'abort'
            except queue.Empty:
                continue
        return False, 'timeout'

    def send_file(self, filepath):
        """Send a file over LoRa. Returns True on success."""
        if not os.path.exists(filepath):
            self.ft_progress_queue.put(('error', 'File not found'))
            return False

        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)

        with open(filepath, 'rb') as f:
            data = f.read()

        file_crc = calculate_crc16(data)
        chunks = [data[i:i+CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]
        total_chunks = len(chunks)

        self.ft_mode = 'send'
        # Clear any stale ACKs
        while not self.ft_queue.empty():
            try:
                self.ft_queue.get_nowait()
            except queue.Empty:
                break

        self.ft_progress_queue.put(('start', filename, total_chunks, filesize))

        # Send FILE header
        header = f'FILE:{filename}:{total_chunks}:{filesize}'
        for retry in range(MAX_RETRIES):
            self.send(header)
            success, reason = self._wait_for_ack(0)
            if success:
                break
        else:
            self.ft_mode = None
            self.ft_progress_queue.put(('error', 'No response from receiver'))
            return False

        # Send chunks
        for seq, chunk in enumerate(chunks, 1):
            chunk_b64 = base64.b64encode(chunk).decode('ascii')
            chunk_crc = calculate_crc16(chunk)
            packet = f'DATA:{seq}:{chunk_crc}:{chunk_b64}'

            for retry in range(MAX_RETRIES):
                self.send(packet)
                success, reason = self._wait_for_ack(seq)
                if success:
                    break
            else:
                self.send('ABORT')
                self.ft_mode = None
                self.ft_progress_queue.put(('error', f'Failed to send chunk {seq}'))
                return False

            progress = seq / total_chunks
            self.ft_progress_queue.put(('progress', progress, seq))

        # Send DONE
        for retry in range(MAX_RETRIES):
            self.send(f'DONE:{file_crc}')
            success, reason = self._wait_for_ack(0)  # Expects OK
            if success and reason == 'ok':
                self.ft_mode = None
                self.ft_progress_queue.put(('done', filepath, filesize))
                return True

        self.ft_mode = None
        self.ft_progress_queue.put(('error', 'No final confirmation'))
        return False

    def get_config(self):
        """Get module configuration (temporarily enters AT mode)."""
        if not self.serial or not self.serial.is_open:
            return None

        self.serial.reset_input_buffer()
        self.serial.write(b'+++\r\n')
        time.sleep(0.5)
        response = self.serial.read(self.serial.in_waiting or 100).decode(errors='ignore')

        config = None
        if 'Entry AT' in response:
            self.serial.write(b'AT+HELP\r\n')
            time.sleep(0.5)
            config = self.serial.read(self.serial.in_waiting or 1000).decode(errors='ignore')

            # Exit AT mode
            self.serial.write(b'+++\r\n')
            time.sleep(0.5)
            self.serial.read(self.serial.in_waiting or 100)
        elif 'Exit AT' in response:
            # We were in AT mode, now in data mode - that's fine
            pass

        self.serial.reset_input_buffer()
        return config


class LoRaGUI:
    """Main GUI application."""

    def __init__(self, root):
        self.root = root
        self.root.title("LoRa Transceiver - DX-LR02")
        self.root.geometry("600x500")
        self.root.minsize(400, 300)

        self.module = None
        self.rx_thread = None

        self.setup_ui()
        self.refresh_ports()

    def setup_ui(self):
        """Create the GUI layout."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Connection frame
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
        conn_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, padx=(0, 5))

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, width=20)
        self.port_combo.grid(row=0, column=1, padx=(0, 5))

        ttk.Button(conn_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=(0, 5))

        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=3, padx=(0, 5))

        ttk.Button(conn_frame, text="Config", command=self.show_config).grid(row=0, column=4)

        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = ttk.Label(conn_frame, textvariable=self.status_var, foreground="red")
        self.status_label.grid(row=0, column=5, padx=(10, 0))

        # Messages frame
        msg_frame = ttk.LabelFrame(main_frame, text="Messages", padding="5")
        msg_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)

        self.messages = scrolledtext.ScrolledText(msg_frame, wrap=tk.WORD, state='disabled')
        self.messages.grid(row=0, column=0, sticky="nsew")
        msg_frame.rowconfigure(0, weight=1)
        msg_frame.columnconfigure(0, weight=1)

        # Configure tags for message styling
        self.messages.tag_configure('sent', foreground='blue')
        self.messages.tag_configure('received', foreground='green')
        self.messages.tag_configure('system', foreground='gray', font=('TkDefaultFont', 9, 'italic'))
        self.messages.tag_configure('error', foreground='red')

        # Send frame
        send_frame = ttk.Frame(main_frame)
        send_frame.grid(row=2, column=0, sticky="ew")

        self.message_var = tk.StringVar()
        self.message_entry = ttk.Entry(send_frame, textvariable=self.message_var)
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.message_entry.bind('<Return>', lambda e: self.send_message())
        send_frame.columnconfigure(0, weight=1)

        self.send_btn = ttk.Button(send_frame, text="Send", command=self.send_message, state='disabled')
        self.send_btn.grid(row=0, column=1)

        # Clear button
        ttk.Button(send_frame, text="Clear", command=self.clear_messages).grid(row=0, column=2, padx=(5, 0))

        # File transfer frame
        ft_frame = ttk.LabelFrame(main_frame, text="File Transfer", padding="5")
        ft_frame.grid(row=3, column=0, sticky="ew", pady=(5, 0))

        self.send_file_btn = ttk.Button(ft_frame, text="Send File...", command=self.send_file, state='disabled')
        self.send_file_btn.grid(row=0, column=0, padx=(0, 10))

        self.ft_status_var = tk.StringVar(value="Ready")
        ttk.Label(ft_frame, textvariable=self.ft_status_var).grid(row=0, column=1, padx=(0, 10))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(ft_frame, variable=self.progress_var, maximum=100, length=200)
        self.progress_bar.grid(row=0, column=2, sticky="ew")
        ft_frame.columnconfigure(2, weight=1)

    def refresh_ports(self):
        """Refresh the list of available serial ports."""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)

    def toggle_connection(self):
        """Connect or disconnect from the module."""
        if self.module and self.module.running:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        """Connect to the selected port."""
        port = self.port_var.get()
        if not port:
            messagebox.showerror("Error", "Please select a port")
            return

        try:
            self.module = LoRaModule(port)
            self.module.connect()

            # Start receive thread
            self.rx_thread = threading.Thread(target=self.module.receive_loop, daemon=True)
            self.rx_thread.start()

            # Start polling for received messages
            self.poll_rx()

            self.connect_btn.configure(text="Disconnect")
            self.send_btn.configure(state='normal')
            self.send_file_btn.configure(state='normal')
            self.status_var.set("Connected")
            self.status_label.configure(foreground="green")

            self.add_message(f"Connected to {port}", 'system')

        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self.module = None

    def disconnect(self):
        """Disconnect from the module."""
        if self.module:
            self.module.disconnect()
            self.module = None

        self.connect_btn.configure(text="Connect")
        self.send_btn.configure(state='disabled')
        self.send_file_btn.configure(state='disabled')
        self.status_var.set("Disconnected")
        self.status_label.configure(foreground="red")

        self.add_message("Disconnected", 'system')

    def poll_rx(self):
        """Poll for received messages and update the GUI."""
        if self.module and self.module.running:
            # Poll chat messages
            try:
                while True:
                    message = self.module.rx_queue.get_nowait()
                    if message.startswith('[ERROR]'):
                        self.add_message(message, 'error')
                    else:
                        self.add_message(f"< {message}", 'received')
            except queue.Empty:
                pass

            # Poll file transfer progress
            try:
                while True:
                    update = self.module.ft_progress_queue.get_nowait()
                    self._handle_ft_update(update)
            except queue.Empty:
                pass

            # Schedule next poll
            self.root.after(100, self.poll_rx)

    def _handle_ft_update(self, update):
        """Handle file transfer progress update."""
        msg_type = update[0]

        if msg_type == 'start':
            _, filename, chunks, size = update
            self.ft_status_var.set(f"Transferring: {filename}")
            self.progress_var.set(0)
            self.send_file_btn.configure(state='disabled')
            self.add_message(f"[FILE] Starting transfer: {filename} ({size} bytes, {chunks} chunks)", 'system')

        elif msg_type == 'progress':
            _, progress, seq = update
            self.progress_var.set(progress * 100)

        elif msg_type == 'done':
            _, path, size = update
            self.ft_status_var.set("Ready")
            self.progress_var.set(100)
            self.send_file_btn.configure(state='normal')
            self.add_message(f"[FILE] Transfer complete: {path} ({size} bytes)", 'system')
            self.root.after(2000, lambda: self.progress_var.set(0))

        elif msg_type == 'error':
            _, error = update
            self.ft_status_var.set("Ready")
            self.progress_var.set(0)
            self.send_file_btn.configure(state='normal')
            self.add_message(f"[FILE] Error: {error}", 'error')

    def send_file(self):
        """Open file dialog and send selected file."""
        if not self.module or not self.module.running:
            return

        filepath = filedialog.askopenfilename(
            title="Select file to send",
            filetypes=[("All files", "*.*")]
        )

        if filepath:
            # Run in background thread to avoid blocking GUI
            thread = threading.Thread(target=self.module.send_file, args=(filepath,), daemon=True)
            thread.start()

    def send_message(self):
        """Send the message in the entry field."""
        message = self.message_var.get().strip()
        if not message:
            return

        if self.module and self.module.send(message):
            self.add_message(f"> {message}", 'sent')
            self.message_var.set("")
        else:
            self.add_message("Failed to send message", 'error')

    def add_message(self, message, tag=''):
        """Add a message to the message display."""
        self.messages.configure(state='normal')
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.messages.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.messages.see(tk.END)
        self.messages.configure(state='disabled')

    def clear_messages(self):
        """Clear all messages."""
        self.messages.configure(state='normal')
        self.messages.delete(1.0, tk.END)
        self.messages.configure(state='disabled')

    def show_config(self):
        """Show module configuration in a popup."""
        if not self.module or not self.module.running:
            messagebox.showinfo("Config", "Connect to a module first")
            return

        config = self.module.get_config()
        if config:
            # Create popup window
            popup = tk.Toplevel(self.root)
            popup.title("Module Configuration")
            popup.geometry("400x350")

            text = scrolledtext.ScrolledText(popup, wrap=tk.WORD)
            text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text.insert(tk.END, config)
            text.configure(state='disabled')
        else:
            messagebox.showwarning("Config", "Could not read configuration")

    def on_closing(self):
        """Handle window close."""
        self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = LoRaGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == '__main__':
    main()
