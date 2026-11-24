"""Known answers from meganz/webclient f1c75714, encrypter.js + condenseMacs."""
import struct
from concurrent.futures import CancelledError

import pytest

from src.downloader.file_integrity import matches_file_mac

KEY = struct.unpack(">4I", bytes(range(16)))
IV = struct.unpack(">2I", bytes(range(16, 24))) + (0, 0)


@pytest.mark.parametrize(("length", "tag"), [
    (0, "0000000000000000"),
    (1, "ca0ad35a0e5ee8b0"),
    (15, "016a6a0c7f4dc731"),
    (16, "81f0acf8c24fb7b4"),
    (17, "1c38ba320f273926"),
    (131071, "ca34706eb109f526"),
    (131072, "2554d9bf92da5549"),
    (131073, "0c3225207e128050"),
    (393216, "1eec5f2475932a47"),
    (4718592, "3629706660819348"),
    (5767185, "39045dff63d441a6"),
    (6291479, "7c4b17cbced589c1"),
])
def test_webclient_vectors(tmp_path, length, tag):
    target = tmp_path / "sample"
    data = (bytes(range(251)) * (length // 251 + 1))[:length]
    target.write_bytes(data)
    assert matches_file_mac(target, length, KEY, IV, bytes.fromhex(tag))
    assert not matches_file_mac(target, length + 1, KEY, IV, bytes.fromhex(tag))
    assert not matches_file_mac(target, length, KEY, IV, bytes.fromhex("96" * 8))


def test_cancel_during_verification(tmp_path):
    path = tmp_path / "sample"
    path.write_bytes(bytes(400_000))
    cancelled = iter([False, True])
    with pytest.raises(CancelledError):
        matches_file_mac(path, 400_000, KEY, IV, bytes(8), lambda: next(cancelled))


@pytest.mark.parametrize("parallel", [False, True])
def test_encrypted_transport_matches_reference_after_reassembly(tmp_path, monkeypatch, parallel):
    import base64

    from Crypto.Cipher import AES
    from src.downloader import mega_client, parallel_client
    from src.downloader.mega_api import MegaPublicClient
    from src.proxy.pool import ProxyPool

    size = 5_767_185
    plaintext = (bytes(range(251)) * (size // 251 + 1))[:size]
    ciphertext = AES.new(bytes(range(16)), AES.MODE_CTR, nonce=bytes(range(16, 24))).encrypt(plaintext)
    suffix = IV[:2] + struct.unpack(">2I", bytes.fromhex("39045dff63d441a6"))
    raw = struct.pack(">8I", *(a ^ b for a, b in zip(KEY, suffix)), *suffix)
    url = "https://mega.nz/file/EXAMPLE1#" + base64.urlsafe_b64encode(raw).decode().rstrip("=")
    proxy = {"host": "localhost", "port": 1, "protocol": "http"}
    monkeypatch.setattr(MegaPublicClient, "_api_request",
                        lambda *args: {"g": "https://example.invalid/data", "s": size})
    requested = []

    class Response:
        status_code = 206

        def __init__(self, start, end):
            self.start, self.end = start, end

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            # Transport packets may end in the middle of an AES block.
            step = chunk_size - 1
            for offset in range(self.start, self.end + 1, step):
                yield ciphertext[offset:min(offset + step, self.end + 1)]

    def get(_url, *, headers, **kwargs):
        if "Range" in headers:
            start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        else:
            start, end = 0, size - 1
        requested.append((start, end))
        return Response(start, end)

    monkeypatch.setattr(mega_client.requests, "get", get)
    if parallel:
        chunk_size = 640 * 1024
        part = tmp_path / "mega_EXAMPLE1.part"
        ranges = parallel_client._split_chunks(size, chunk_size)
        resumed = {ranges[0], ranges[2]}
        with part.open("wb") as f:
            f.truncate(size)
            for start, end in resumed:
                f.seek(start)
                f.write(plaintext[start:end + 1])
        parallel_client._save_progress(part, "EXAMPLE1", size, resumed, chunk_size)
        pool = ProxyPool()
        monkeypatch.setattr(pool, "get_next", lambda: proxy)
        client = parallel_client.ParallelMegaDownloader(pool, 2, chunk_size=chunk_size)
        final = client.download(url, tmp_path, proxy)
        assert sorted(requested) == sorted(set(ranges) - resumed)
    else:
        final = mega_client.MegaClient(proxy).download(url, tmp_path)
        assert requested == [(0, size - 1)]
    assert final.read_bytes() == plaintext
