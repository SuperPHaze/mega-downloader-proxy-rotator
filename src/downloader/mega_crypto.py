# Primitive crypto Mega vendorizzate da mega.py 1.0.8 (file `mega/crypto.py`).
# Solo helper puri (no I/O, no stato globale) effettivamente usati dai client.
from __future__ import annotations

import base64
import json
import struct

from Crypto.Cipher import AES

from src.core.errors import UserFacingValueError


def base64_url_decode(data: str) -> bytes:
    data += "=="[(2 - len(data) * 3) % 4:]
    for search, replace in (("-", "+"), ("_", "/"), (",", "")):
        data = data.replace(search, replace)
    return base64.b64decode(data)


def a32_to_str(a: tuple[int, ...]) -> bytes:
    return struct.pack(">%dI" % len(a), *a)


def _str_to_a32(b: bytes) -> tuple[int, ...]:
    if len(b) % 4:
        b += b"\0" * (4 - len(b) % 4)
    return struct.unpack(">%dI" % (len(b) // 4), b)


def base64_to_a32(s: str) -> tuple[int, ...]:
    return _str_to_a32(base64_url_decode(s))


def decrypt_attr(data: bytes, key: tuple[int, ...]) -> dict | None:
    """Decifra il blob attributi Mega (AES-CBC, IV=0). Ritorna None su parse fail."""
    try:
        aes = AES.new(a32_to_str(key), AES.MODE_CBC, b"\0" * 16)
        plain = aes.decrypt(data)
        text = plain.decode("latin-1").rstrip("\0")
        if text[:6] != 'MEGA{"':
            return None
        parsed = json.loads(text[4:])
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def decrypt_key(enc: tuple[int, ...], master: tuple[int, ...]) -> tuple[int, ...]:
    """Decifra la chiave di un nodo con la master key della cartella condivisa.

    Semantica Mega: AES a BLOCCHI INDIPENDENTI da 16 byte (4 word), cioe' ECB
    (equivalente a CBC con IV azzerato *rifatto per ogni blocco*, come in
    decrypt_attr). Una singola CBC su 32 byte sbaglierebbe il secondo blocco:
    e' l'errore classico nell'implementare le cartelle Mega.

    Ritorna 4 word (nodo cartella) o 8 word (nodo file, da passare a
    derive_file_key).
    """
    if not enc or len(enc) % 4 != 0:
        raise UserFacingValueError("crypto_bad_key_length", words=len(enc))
    if len(master) != 4:
        raise UserFacingValueError("crypto_bad_master_key", words=len(master))
    aes = AES.new(a32_to_str(master), AES.MODE_ECB)
    return _str_to_a32(aes.decrypt(a32_to_str(enc)))


def derive_file_key(raw_key: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Da `file_key` a 8 word ricava (k, iv) per AES-CTR del payload file.

    k = XOR fra le due meta' (4 word). iv = (raw[4], raw[5], 0, 0).
    """
    if len(raw_key) < 8:
        raise UserFacingValueError("crypto_file_key_short", words=len(raw_key))
    k = (
        raw_key[0] ^ raw_key[4],
        raw_key[1] ^ raw_key[5],
        raw_key[2] ^ raw_key[6],
        raw_key[3] ^ raw_key[7],
    )
    iv = (raw_key[4], raw_key[5], 0, 0)
    return k, iv
