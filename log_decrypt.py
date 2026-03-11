#!/usr/bin/env python3
"""Decrypt phone fields in a PhoneInfo app.log file.

Usage:
    python log_decrypt.py <logfile> <base64_key>
    python log_decrypt.py <logfile> --key-env LOG_KEY

The key can also be piped to avoid it appearing in the process list:
    echo "$LOG_KEY" | python log_decrypt.py <logfile> -

Creates <logfile>.clear with the phone column decrypted in place.
Rows whose phone field is masked (e.g. *****1234) or plain text are
left unchanged — only valid AES-256-ECB base64 ciphertexts are touched.
"""

import base64
import csv
import re
import sys
from pathlib import Path

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    sys.exit("pycryptodome is required: pip install pycryptodome")

# Column index of the phone field in app.log (0-based)
# Header: datetime,user,action,filename,phone,...
PHONE_COL = 4

# A base64 string whose decoded length is a non-zero multiple of 16 bytes
# (one AES block = 16 bytes → 24 base64 chars; two blocks → 44 chars, etc.)
_B64 = re.compile(r'^[A-Za-z0-9+/]+=*$')


def _try_decrypt(value: str, key: bytes) -> str | None:
    """Return decrypted plaintext if value is an AES-256-ECB base64 ciphertext, else None."""
    if not _B64.match(value):
        return None
    try:
        ct = base64.b64decode(value)
    except Exception:
        return None
    if not ct or len(ct) % AES.block_size != 0:
        return None
    try:
        plain = unpad(AES.new(key, AES.MODE_ECB).decrypt(ct), AES.block_size)
        return plain.decode("ascii")
    except Exception:
        return None


def decrypt_log(log_path: Path, key: bytes) -> Path:
    out_path = log_path.parent / (log_path.name + ".clear")
    decrypted_count = 0
    skipped_count = 0

    with (
        log_path.open("r", encoding="utf-8", newline="") as fin,
        out_path.open("w", encoding="utf-8", newline="") as fout,
    ):
        reader = csv.reader(fin)
        writer = csv.writer(fout)

        for row_num, row in enumerate(reader):
            # Header row or rows too short to have a phone column — pass through
            if row_num == 0 or len(row) <= PHONE_COL:
                writer.writerow(row)
                continue

            phone_field = row[PHONE_COL]
            plain = _try_decrypt(phone_field, key)
            if plain is not None:
                row[PHONE_COL] = plain
                decrypted_count += 1
            else:
                skipped_count += 1

            writer.writerow(row)

    return out_path, decrypted_count, skipped_count


def _load_key(arg: str) -> bytes:
    """Resolve key from: base64 string, '-' (read from stdin), or --key-env NAME."""
    if arg == "-":
        raw = sys.stdin.readline().strip()
    elif arg.startswith("env:"):
        import os
        env_name = arg[4:]
        raw = os.environ.get(env_name, "")
        if not raw:
            sys.exit(f"Error: environment variable {env_name!r} is not set")
    else:
        raw = arg

    try:
        key = base64.b64decode(raw)
    except Exception:
        sys.exit("Error: key is not valid base64")

    if len(key) not in (16, 24, 32):
        sys.exit(f"Error: decoded key must be 16, 24, or 32 bytes (got {len(key)})")

    return key


def main():
    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "  python log_decrypt.py <logfile> <base64_key>\n"
            "  python log_decrypt.py <logfile> env:LOG_KEY   # read key from env var\n"
            "  echo $KEY | python log_decrypt.py <logfile> - # read key from stdin",
            file=sys.stderr,
        )
        sys.exit(1)

    log_path = Path(sys.argv[1])
    if not log_path.is_file():
        sys.exit(f"Error: {log_path} is not a file")

    key = _load_key(sys.argv[2])

    out_path, decrypted, skipped = decrypt_log(log_path, key)
    print(f"Written : {out_path}")
    print(f"Decrypted: {decrypted} phone(s)")
    print(f"Skipped  : {skipped} (masked or plain text)")


if __name__ == "__main__":
    main()
