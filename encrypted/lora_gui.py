#!/usr/bin/env python3
"""
LoRa Encrypted Full-Duplex GUI Application for DX-LR02 modules.
Uses AES-256-GCM encryption with pre-shared key.

A simple chat-like interface for bidirectional encrypted LoRa communication.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import serial
import serial.tools.list_ports
import threading
import queue
import time
from datetime import datetime
import crypto_utils


class LoRaModule:
    """Handles serial communication with the DX-LR02 LoRa module."""

    def __init__(self, port, baud=9600):
        self.port = port
        self.baud = baud
        self.serial = None
        self.running = False
        self.rx_queue = queue.Queue()
        self.encryption_key = None

    def set_encryption_key(self, key):
        """Set the encryption key."""
        self.encryption_key = key

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
        """Encrypt and send a message over LoRa."""
        if self.serial and self.serial.is_open and self.encryption_key:
            encrypted = crypto_utils.encrypt(message, self.encryption_key)
            self.serial.write((encrypted + '\r\n').encode('utf-8'))
            return True
        return False

    def receive_loop(self):
        """Background loop to receive and decrypt messages."""
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
                            # Try to decrypt
                            if crypto_utils.is_encrypted(line):
                                decrypted = crypto_utils.decrypt(line, self.encryption_key)
                                if decrypted:
                                    self.rx_queue.put(('encrypted', decrypted))
                                else:
                                    self.rx_queue.put(('decrypt_failed', line[:50] + '...'))
                            else:
                                self.rx_queue.put(('unencrypted', line))
                time.sleep(0.05)
            except Exception as e:
                if self.running:
                    self.rx_queue.put(('error', str(e)))
                break

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
        self.root.title("LoRa Encrypted Transceiver - DX-LR02")
        self.root.geometry("650x550")
        self.root.minsize(500, 400)

        self.module = None
        self.rx_thread = None
        self.encryption_key = None

        # Check crypto library
        if not crypto_utils.check_crypto_available():
            messagebox.showerror("Error", "No encryption library found!\nInstall with: pip install cryptography")
            root.destroy()
            return

        # Load or create encryption key
        self.encryption_key = crypto_utils.get_or_create_key()

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

        ttk.Button(conn_frame, text="Config", command=self.show_config).grid(row=0, column=4, padx=(0, 5))

        ttk.Button(conn_frame, text="Key", command=self.manage_key).grid(row=0, column=5)

        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = ttk.Label(conn_frame, textvariable=self.status_var, foreground="red")
        self.status_label.grid(row=0, column=6, padx=(10, 0))

        # Encryption status
        enc_frame = ttk.Frame(main_frame)
        enc_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))

        self.key_status = ttk.Label(enc_frame, text="\U0001F512 AES-256-GCM Encryption Active", foreground="green")
        self.key_status.grid(row=0, column=0)

        self.key_short = ttk.Label(enc_frame, text=f"Key: {crypto_utils.key_to_hex(self.encryption_key)[:16]}...", foreground="gray")
        self.key_short.grid(row=0, column=1, padx=(20, 0))

        # Messages frame
        msg_frame = ttk.LabelFrame(main_frame, text="Messages", padding="5")
        msg_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 5))
        main_frame.rowconfigure(2, weight=1)
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
        self.messages.tag_configure('warning', foreground='orange')

        # Send frame
        send_frame = ttk.Frame(main_frame)
        send_frame.grid(row=3, column=0, sticky="ew")

        self.message_var = tk.StringVar()
        self.message_entry = ttk.Entry(send_frame, textvariable=self.message_var)
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.message_entry.bind('<Return>', lambda e: self.send_message())
        send_frame.columnconfigure(0, weight=1)

        self.send_btn = ttk.Button(send_frame, text="Send", command=self.send_message, state='disabled')
        self.send_btn.grid(row=0, column=1)

        # Clear button
        ttk.Button(send_frame, text="Clear", command=self.clear_messages).grid(row=0, column=2, padx=(5, 0))

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
            self.module.set_encryption_key(self.encryption_key)
            self.module.connect()

            # Start receive thread
            self.rx_thread = threading.Thread(target=self.module.receive_loop, daemon=True)
            self.rx_thread.start()

            # Start polling for received messages
            self.poll_rx()

            self.connect_btn.configure(text="Disconnect")
            self.send_btn.configure(state='normal')
            self.status_var.set("Connected")
            self.status_label.configure(foreground="green")

            self.add_message(f"Connected to {port} (encrypted)", 'system')

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
        self.status_var.set("Disconnected")
        self.status_label.configure(foreground="red")

        self.add_message("Disconnected", 'system')

    def poll_rx(self):
        """Poll for received messages and update the GUI."""
        if self.module and self.module.running:
            try:
                while True:
                    msg_type, message = self.module.rx_queue.get_nowait()
                    if msg_type == 'encrypted':
                        self.add_message(f"\U0001F512 < {message}", 'received')
                    elif msg_type == 'decrypt_failed':
                        self.add_message(f"\U0001F510 [Decryption failed] {message}", 'error')
                    elif msg_type == 'unencrypted':
                        self.add_message(f"\U000026A0 [UNENCRYPTED] {message}", 'warning')
                    elif msg_type == 'error':
                        self.add_message(f"[ERROR] {message}", 'error')
            except queue.Empty:
                pass

            # Schedule next poll
            self.root.after(100, self.poll_rx)

    def send_message(self):
        """Send the message in the entry field."""
        message = self.message_var.get().strip()
        if not message:
            return

        if self.module and self.module.send(message):
            self.add_message(f"\U0001F512 > {message}", 'sent')
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

    def manage_key(self):
        """Show key management dialog."""
        popup = tk.Toplevel(self.root)
        popup.title("Encryption Key Management")
        popup.geometry("500x200")
        popup.transient(self.root)

        frame = ttk.Frame(popup, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Current Key (share this with other devices):").pack(anchor='w')

        key_hex = crypto_utils.key_to_hex(self.encryption_key)
        key_entry = ttk.Entry(frame, width=70)
        key_entry.insert(0, key_hex)
        key_entry.configure(state='readonly')
        key_entry.pack(fill='x', pady=(5, 10))

        def copy_key():
            self.root.clipboard_clear()
            self.root.clipboard_append(key_hex)
            messagebox.showinfo("Copied", "Key copied to clipboard")

        def import_key():
            new_key = simpledialog.askstring("Import Key", "Paste the 64-character hex key:", parent=popup)
            if new_key:
                try:
                    self.encryption_key = crypto_utils.set_key_from_hex(new_key)
                    if self.module:
                        self.module.set_encryption_key(self.encryption_key)
                    self.key_short.configure(text=f"Key: {new_key[:16]}...")
                    messagebox.showinfo("Success", "Key imported successfully")
                    popup.destroy()
                except ValueError as e:
                    messagebox.showerror("Error", str(e))

        def generate_new():
            if messagebox.askyesno("Confirm", "Generate a new key? You'll need to share it with other devices."):
                self.encryption_key = crypto_utils.generate_key()
                crypto_utils.save_key(self.encryption_key)
                if self.module:
                    self.module.set_encryption_key(self.encryption_key)
                new_hex = crypto_utils.key_to_hex(self.encryption_key)
                key_entry.configure(state='normal')
                key_entry.delete(0, tk.END)
                key_entry.insert(0, new_hex)
                key_entry.configure(state='readonly')
                self.key_short.configure(text=f"Key: {new_hex[:16]}...")
                messagebox.showinfo("New Key", f"New key generated. Share it with other devices.")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x', pady=(10, 0))

        ttk.Button(btn_frame, text="Copy", command=copy_key).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="Import Key", command=import_key).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="Generate New", command=generate_new).pack(side='left')

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
