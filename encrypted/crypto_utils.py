#!/usr/bin/env python3
"""
Encryption utilities for LoRa communication.
Uses AES-256-GCM with pre-shared key.
"""

import os
import base64
import hashlib
from pathlib import Path

# Try cryptography library first, fall back to pycryptodome
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_LIB = 'cryptography'
except ImportError:
    try:
        from Crypto.Cipher import AES
        CRYPTO_LIB = 'pycryptodome'
    except ImportError:
        CRYPTO_LIB = None

# Key file location
KEY_FILE = Path(__file__).parent / '.lora_key'

# Message prefix to identify encrypted messages
ENCRYPTED_PREFIX = 'ENC:'


def check_crypto_available():
    """Check if encryption libraries are available."""
    if CRYPTO_LIB is None:
        print("[!] No encryption library found!")
        print("[!] Install with: pip install cryptography")
        print("[!] Or: pip install pycryptodome")
        return False
    return True


def generate_key():
    """Generate a new 256-bit key."""
    return os.urandom(32)


def key_to_hex(key: bytes) -> str:
    """Convert key bytes to hex string for display/sharing."""
    return key.hex()


def hex_to_key(hex_str: str) -> bytes:
    """Convert hex string back to key bytes."""
    return bytes.fromhex(hex_str.strip())


def save_key(key: bytes, path: Path = KEY_FILE):
    """Save key to file (hex encoded)."""
    path.write_text(key_to_hex(key))
    # Restrict permissions (owner read/write only)
    path.chmod(0o600)


def load_key(path: Path = KEY_FILE) -> bytes:
    """Load key from file."""
    if not path.exists():
        return None
    return hex_to_key(path.read_text())


def get_or_create_key() -> bytes:
    """Get existing key or create new one."""
    key = load_key()
    if key is None:
        print("[*] No encryption key found. Generating new key...")
        key = generate_key()
        save_key(key)
        print(f"[*] Key saved to {KEY_FILE}")
        print(f"[*] Share this key with other devices:")
        print(f"    {key_to_hex(key)}")
    return key


def set_key_from_hex(hex_str: str):
    """Set key from hex string (for importing shared key)."""
    key = hex_to_key(hex_str)
    if len(key) != 32:
        raise ValueError("Key must be 64 hex characters (256 bits)")
    save_key(key)
    print(f"[*] Key imported and saved to {KEY_FILE}")
    return key


def encrypt(plaintext: str, key: bytes) -> str:
    """
    Encrypt plaintext string.
    Returns base64-encoded string: nonce (12 bytes) + ciphertext + tag (16 bytes)
    """
    if CRYPTO_LIB == 'cryptography':
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        # ciphertext includes the tag
        encrypted = nonce + ciphertext
    elif CRYPTO_LIB == 'pycryptodome':
        nonce = os.urandom(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
        encrypted = nonce + ciphertext + tag
    else:
        raise RuntimeError("No crypto library available")

    return ENCRYPTED_PREFIX + base64.b64encode(encrypted).decode('ascii')


def decrypt(encrypted_msg: str, key: bytes) -> str:
    """
    Decrypt base64-encoded encrypted message.
    Returns plaintext string or None if decryption fails.
    """
    if not encrypted_msg.startswith(ENCRYPTED_PREFIX):
        return None  # Not an encrypted message

    try:
        encrypted = base64.b64decode(encrypted_msg[len(ENCRYPTED_PREFIX):])
        nonce = encrypted[:12]
        ciphertext_with_tag = encrypted[12:]

        if CRYPTO_LIB == 'cryptography':
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        elif CRYPTO_LIB == 'pycryptodome':
            ciphertext = ciphertext_with_tag[:-16]
            tag = ciphertext_with_tag[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        else:
            return None

        return plaintext.decode('utf-8')
    except Exception as e:
        # Decryption failed - wrong key, corrupted message, or tampered
        return None


def is_encrypted(msg: str) -> bool:
    """Check if message is encrypted."""
    return msg.startswith(ENCRYPTED_PREFIX)


# Quick test
if __name__ == '__main__':
    if not check_crypto_available():
        exit(1)

    print(f"[*] Using crypto library: {CRYPTO_LIB}")

    # Test encryption/decryption
    test_key = generate_key()
    print(f"[*] Test key: {key_to_hex(test_key)}")

    test_msg = "Hello, encrypted LoRa!"
    print(f"[*] Original: {test_msg}")

    encrypted = encrypt(test_msg, test_key)
    print(f"[*] Encrypted: {encrypted}")
    print(f"[*] Encrypted length: {len(encrypted)} chars")

    decrypted = decrypt(encrypted, test_key)
    print(f"[*] Decrypted: {decrypted}")

    # Test with wrong key
    wrong_key = generate_key()
    bad_decrypt = decrypt(encrypted, wrong_key)
    print(f"[*] Wrong key decrypt: {bad_decrypt}")

    print("\n[*] All tests passed!" if decrypted == test_msg else "\n[!] Test failed!")
