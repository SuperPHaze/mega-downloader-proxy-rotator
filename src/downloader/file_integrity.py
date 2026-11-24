"""Verify MEGA's file meta-MAC over the plaintext that will be published."""
from __future__ import annotations

import hmac
import os
import struct
from collections.abc import Callable
from concurrent.futures import CancelledError
from pathlib import Path

from Crypto.Cipher import AES

from src.core.errors import UserFacingRuntimeError
from src.downloader.mega_crypto import a32_to_str


class FileIntegrityError(UserFacingRuntimeError):
    """The downloaded data did not match its file key."""


def matches_file_mac(
    path: Path, size: int, key: tuple[int, ...], iv: tuple[int, ...],
    expected_mac: bytes, should_abort: Callable[[], bool] | None = None,
) -> bool:
    """Use MEGA's chunk boundaries, independent of the HTTP ranges and checkpoint."""
    aes_key = a32_to_str(key)
    chunk_iv = a32_to_str(iv[:2]) * 2
    fold = AES.new(aes_key, AES.MODE_CBC, iv=bytes(16))
    state = bytes(16)
    chunk_size = 128 * 1024
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size != size:
            return False
        remaining = size
        while remaining:
            if should_abort and should_abort():
                raise CancelledError()
            length = min(chunk_size, remaining)
            chunk = stream.read(length)
            if len(chunk) != length:
                return False
            # Only the final AES block is zero-padded. Aligned chunks get no padding.
            if length % 16:
                chunk += bytes(16 - length % 16)
            chunk_cipher = AES.new(aes_key, AES.MODE_CBC, iv=chunk_iv)
            chunk_mac = chunk_cipher.encrypt(chunk)[-16:]
            state = fold.encrypt(chunk_mac)
            remaining -= length
            chunk_size = min(chunk_size + 128 * 1024, 1024 * 1024)
        if stream.read(1):
            return False
    if should_abort and should_abort():
        raise CancelledError()
    a, b, c, d = struct.unpack(">4I", state)
    return hmac.compare_digest(struct.pack(">2I", a ^ b, c ^ d), expected_mac)


def promote_verified(
    part: Path, final: Path, size: int, key: tuple[int, ...], iv: tuple[int, ...],
    expected_mac: bytes, should_abort: Callable[[], bool] | None = None,
) -> None:
    if not matches_file_mac(part, size, key, iv, expected_mac, should_abort):
        # Invalidate the journal first. A crash between the unlinks must never
        # turn rejected ranges into resumable ones.
        part.with_name(part.name + ".progress.json").unlink(missing_ok=True)
        part.unlink(missing_ok=True)
        raise FileIntegrityError("file_mac_mismatch")
    os.replace(part, final)
