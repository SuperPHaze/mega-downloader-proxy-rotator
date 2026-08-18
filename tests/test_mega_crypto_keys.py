# Test su decrypt_key: la primitiva che sblocca le chiavi dei nodi di una
# cartella condivisa. Nessuna rete: i vettori sono costruiti cifrando con le
# stesse primitive (AES a blocchi indipendenti da 16 byte).
import pytest
from Crypto.Cipher import AES

from src.downloader.mega_crypto import (
    a32_to_str,
    _str_to_a32,
    decrypt_key,
    derive_file_key,
)

MASTER = (0x01020304, 0x05060708, 0x090A0B0C, 0x0D0E0F10)


def _encrypt_blocks(plain: tuple[int, ...], master: tuple[int, ...]) -> tuple[int, ...]:
    """Cifra a blocchi INDIPENDENTI da 4 word (= ECB), come fa Mega."""
    aes = AES.new(a32_to_str(master), AES.MODE_ECB)
    return _str_to_a32(aes.encrypt(a32_to_str(plain)))


def test_round_trip_single_block_folder_key():
    plain = (0x11111111, 0x22222222, 0x33333333, 0x44444444)
    assert decrypt_key(_encrypt_blocks(plain, MASTER), MASTER) == plain


def test_round_trip_two_blocks_file_key():
    plain = (1, 2, 3, 4, 5, 6, 7, 8)
    assert decrypt_key(_encrypt_blocks(plain, MASTER), MASTER) == plain


def test_second_block_is_independent_not_cbc_chained():
    # Vincolo centrale: i due blocchi da 16 byte sono INDIPENDENTI. Con una CBC
    # unica su 32 byte il secondo blocco uscirebbe diverso: qui deve invece
    # coincidere con la decifratura del blocco preso da solo.
    plain = (0xAAAAAAAA, 0xBBBBBBBB, 0xCCCCCCCC, 0xDDDDDDDD,
             0x11111111, 0x22222222, 0x33333333, 0x44444444)
    enc = _encrypt_blocks(plain, MASTER)
    full = decrypt_key(enc, MASTER)
    second_alone = decrypt_key(enc[4:], MASTER)
    assert full[4:] == second_alone == plain[4:]


def test_identical_blocks_encrypt_identically():
    # Corollario dell'indipendenza dei blocchi: due blocchi uguali in chiaro
    # danno due blocchi uguali cifrati (impossibile con una CBC concatenata).
    block = (7, 7, 7, 7)
    enc = _encrypt_blocks(block + block, MASTER)
    assert enc[:4] == enc[4:]


def test_decrypted_file_key_feeds_derive_file_key():
    plain = (0x0F0F0F0F, 0x10101010, 0x20202020, 0x30303030,
             0x01010101, 0x02020202, 0x03030303, 0x04040404)
    got = decrypt_key(_encrypt_blocks(plain, MASTER), MASTER)
    k, iv = derive_file_key(got)
    assert k == (
        plain[0] ^ plain[4], plain[1] ^ plain[5],
        plain[2] ^ plain[6], plain[3] ^ plain[7],
    )
    assert iv == (plain[4], plain[5], 0, 0)


def test_rejects_non_multiple_of_four_words():
    with pytest.raises(ValueError):
        decrypt_key((1, 2, 3), MASTER)
    with pytest.raises(ValueError):
        decrypt_key((), MASTER)


def test_rejects_master_key_of_wrong_length():
    with pytest.raises(ValueError):
        decrypt_key((1, 2, 3, 4), (1, 2, 3, 4, 5, 6, 7, 8))
