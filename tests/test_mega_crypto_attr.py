# Test su decrypt_attr: la lettura del nome file dal blob attributi Mega
# (AES-CBC, IV=0). Nessuna rete: i vettori sono costruiti cifrando con le
# stesse primitive, piu' un caso REALE catturato dal bug (vedi sotto).
from Crypto.Cipher import AES

from src.downloader.mega_crypto import a32_to_str, decrypt_attr

KEY = (0x01020304, 0x05060708, 0x090A0B0C, 0x0D0E0F10)
OTHER_KEY = (0xAAAAAAAA, 0xBBBBBBBB, 0xCCCCCCCC, 0xDDDDDDDD)


def _encrypt_attr(json_body: str, key=KEY, pad: bytes = b"") -> bytes:
    """Cifra 'MEGA' + json_body (+ padding esplicito) come fa Mega.

    Con `pad=b""` il chiamante e' responsabile di arrivare a un multiplo di
    16 byte: di norma Mega zero-paddа, ma un file rinominato lato server puo'
    lasciare residuo di cifratura del nome precedente (byte non-zero) dopo il
    terminatore — e' esattamente il caso coperto da `pad` non-nullo qui sotto.
    """
    plain = ("MEGA" + json_body).encode("utf-8") + pad
    if len(plain) % 16:
        plain += b"\0" * (16 - len(plain) % 16)
    aes = AES.new(a32_to_str(key), AES.MODE_CBC, b"\0" * 16)
    return aes.encrypt(plain)


def test_clean_zero_padded_blob_returns_name():
    data = _encrypt_attr('{"n":"video.mkv"}')
    assert decrypt_attr(data, KEY) == {"n": "video.mkv"}


def test_trailing_non_zero_garbage_after_json_is_ignored():
    # Il difetto osservato: dopo la '}' di chiusura resta un byte nullo poi
    # residuo non-zero (avanzo del nome precedente, file rinominato lato
    # Mega). La lettura strict di tutta la stringa come JSON falliva con
    # "Extra data" e faceva ripiegare su mega_<handle> a chiave e nome giusti.
    data = _encrypt_attr('{"n":"video.mkv"}', pad=b"\x00garbage-tail")
    assert decrypt_attr(data, KEY) == {"n": "video.mkv"}


def test_real_captured_case_jr0jjszk():
    # Blob reale catturato dal caso segnalato (handle jR0jjSZK): il file si
    # apre correttamente in VLC (chiave e contenuto integri), ma il nome
    # ripiegava su "mega_jR0jjSZK". Ciphertext e chiave derivata (k) sono
    # quelli osservati dal vivo via l'API pubblica Mega (nessuna rete qui).
    data = bytes.fromhex(
        "c4fed604ce61745ac92e4f5920989c79f9862131a635b84998a5e4ebd295b15"
        "869fad8d6f33d0fd5efb42a88ba5c304ce94cf1f2e26f332df53f0537647bca"
        "62dad334bc2005e19aea3bba59babc0a1c28c3746e2e9eb3665f90268e9150b"
        "124"
    )
    real_k = (1225266824, 3889101925, 344022962, 2764362391)
    assert decrypt_attr(data, real_k) == {
        "n": "We.Were.Soldiers.Fino.All.Ultimo.Uomo.2002.ITA-ENG.BRRip.720p.x264-P92.mkv"
    }


def test_accented_name_round_trips_as_utf8_not_mojibake():
    data = _encrypt_attr('{"n":"caff\\u00e8 con panna.mkv"}')
    assert decrypt_attr(data, KEY) == {"n": "caffè con panna.mkv"}


def test_wrong_key_falls_back_cleanly_to_none():
    data = _encrypt_attr('{"n":"video.mkv"}')
    assert decrypt_attr(data, OTHER_KEY) is None


def test_wrong_key_with_trailing_garbage_still_falls_back_cleanly():
    data = _encrypt_attr('{"n":"video.mkv"}', pad=b"\x00garbage-tail")
    assert decrypt_attr(data, OTHER_KEY) is None
