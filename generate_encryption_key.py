#!/usr/bin/env python3
"""
Generate a secure encryption key for database encryption.
Run this once and add the key to your .env file.
"""

import secrets
import base64

def generate_key(length=32):
    """
    Generate a cryptographically secure random key (base64-encoded).

    Args:
        length: Number of random bytes (default 32 = 256-bit key)

    Returns:
        str: Base64-encoded key safe for config files
    """
    random_bytes = secrets.token_bytes(length)
    return base64.b64encode(random_bytes).decode('ascii')

if __name__ == "__main__":
    print("=" * 70)
    print("PhoneInfo Database Encryption Key Generator")
    print("=" * 70)
    print()

    key = generate_key(32)

    print("Your encryption key (base64-encoded, 256-bit):")
    print()
    print(f"DB_ENCRYPTION_KEY={key}")
    print()
    print("=" * 70)
    print("IMPORTANT:")
    print("  1. Add this to your .env file")
    print("  2. NEVER commit this key to git")
    print("  3. Store it securely (password manager, secrets vault)")
    print("  4. If you lose this key, your encrypted database is UNRECOVERABLE")
    print()
    print("Base64 format:")
    print("  - Safe for config files (no special shell characters)")
    print("  - 32 bytes = 256-bit security")
    print("  - URL-safe, no escaping needed")
    print("=" * 70)
