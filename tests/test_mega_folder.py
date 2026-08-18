# Test sull'espansione di una cartella Mega: ricostruzione dell'albero,
# sanificazione dei segmenti, collisioni, sotto-selezione, cap.
#
# Nessuna rete: la risposta `f` dell'API viene FABBRICATA cifrando nomi e
# chiavi con le stesse primitive usate in produzione, cosi' il test esercita
# davvero decrypt_key/decrypt_attr e non una loro imitazione.
import base64
import json

import pytest
from Crypto.Cipher import AES

from src.core.mega_links import parse_folder_job_url
from src.downloader.mega_crypto import a32_to_str, derive_file_key
from src.downloader.mega_folder import (
    MegaFolderError,
    build_folder_expansion,
    deduplicate_job_urls,
)

FOLDER_ID = "FOLDERID"
MASTER = (0x01020304, 0x05060708, 0x090A0B0C, 0x0D0E0F10)


# ---- helper di costruzione della risposta `f` ------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _enc_key(plain: tuple[int, ...]) -> str:
    aes = AES.new(a32_to_str(MASTER), AES.MODE_ECB)
    return _b64(aes.encrypt(a32_to_str(plain)))


def _enc_attr(name: str, key: tuple[int, ...]) -> str:
    payload = ('MEGA' + json.dumps({"n": name}, ensure_ascii=False)).encode("utf-8")
    payload += b"\0" * (-len(payload) % 16)
    aes = AES.new(a32_to_str(key), AES.MODE_CBC, b"\0" * 16)
    return _b64(aes.encrypt(payload))


def _folder_key(seed: int) -> tuple[int, ...]:
    return (seed, seed + 1, seed + 2, seed + 3)


def _file_key(seed: int) -> tuple[int, ...]:
    return tuple(seed + i for i in range(8))


def root_node(name: str = "Mia Cartella") -> dict:
    # Il nodo radice di una share ha gli attributi cifrati con la master key.
    return {"h": FOLDER_ID, "t": 2, "a": _enc_attr(name, MASTER)}


def folder_node(handle: str, parent: str, name: str, seed: int = 100) -> dict:
    key = _folder_key(seed)
    return {
        "h": handle, "p": parent, "t": 1,
        "k": f"{FOLDER_ID}:{_enc_key(key)}",
        "a": _enc_attr(name, key),
    }


def file_node(handle: str, parent: str, name: str, size: int = 1234, seed: int = 200) -> dict:
    key = _file_key(seed)
    attr_key, _iv = derive_file_key(key)
    return {
        "h": handle, "p": parent, "t": 0, "s": size,
        "k": f"{FOLDER_ID}:{_enc_key(key)}",
        "a": _enc_attr(name, attr_key),
    }


def _expand(nodes, **kwargs):
    return build_folder_expansion(FOLDER_ID, MASTER, nodes, **kwargs)


def _paths(expansion):
    return ["/".join(f.rel_path) for f in expansion.files]


# ---- albero ----------------------------------------------------------------

def test_flat_folder():
    exp = _expand([
        root_node(),
        file_node("F1", FOLDER_ID, "uno.bin"),
        file_node("F2", FOLDER_ID, "due.bin", seed=300),
    ])
    assert exp.folder_name == "Mia Cartella"
    assert _paths(exp) == ["Mia Cartella/due.bin", "Mia Cartella/uno.bin"]
    assert exp.total_files == 2 and exp.n_folders == 0


def test_nested_subfolders_multi_level():
    exp = _expand([
        root_node("Radice"),
        folder_node("D1", FOLDER_ID, "livello1", seed=100),
        folder_node("D2", "D1", "livello2", seed=110),
        folder_node("D3", "D2", "livello3", seed=120),
        file_node("F1", "D3", "profondo.bin", seed=200),
        file_node("F2", FOLDER_ID, "superficie.bin", seed=210),
    ])
    assert set(_paths(exp)) == {
        "Radice/livello1/livello2/livello3/profondo.bin",
        "Radice/superficie.bin",
    }
    assert exp.n_folders == 3


def test_empty_folder_yields_no_files():
    exp = _expand([root_node("Vuota")])
    assert exp.files == () and exp.total_files == 0
    assert exp.folder_name == "Vuota"


def test_folder_with_only_subfolders_is_empty_of_files():
    exp = _expand([root_node(), folder_node("D1", FOLDER_ID, "solo cartelle")])
    assert exp.files == () and exp.n_folders == 1


def test_file_sizes_are_preserved():
    exp = _expand([root_node(), file_node("F1", FOLDER_ID, "x.bin", size=987654321)])
    assert exp.files[0].size == 987654321


def test_zero_byte_file_is_kept():
    exp = _expand([root_node(), file_node("F1", FOLDER_ID, "vuoto.txt", size=0)])
    assert exp.files[0].size == 0


def test_ordering_is_deterministic():
    nodes = [
        root_node(),
        file_node("F3", FOLDER_ID, "zeta.bin", seed=300),
        file_node("F1", FOLDER_ID, "alfa.bin", seed=200),
        file_node("F2", FOLDER_ID, "mezzo.bin", seed=400),
    ]
    assert _paths(_expand(nodes)) == _paths(_expand(list(reversed(nodes))))


# ---- nomi non sicuri e collisioni ------------------------------------------

def test_unsafe_names_are_sanitized_per_segment():
    exp = _expand([
        root_node("cart:ella?"),
        folder_node("D1", FOLDER_ID, 'sub<>|dir', seed=100),
        file_node("F1", "D1", 'fi:le"?.bin', seed=200),
    ])
    path = "/".join(exp.files[0].rel_path)
    assert not any(c in path for c in '<>:"\\|?*')
    assert path.endswith(".bin")


def test_path_traversal_in_names_is_neutralized():
    exp = _expand([
        root_node(".."),
        folder_node("D1", FOLDER_ID, "..", seed=100),
        file_node("F1", "D1", "../../evil.bin", seed=200),
    ])
    rel = exp.files[0].rel_path
    assert ".." not in rel
    assert rel[-1] == "evil.bin"


def test_windows_reserved_device_name_is_escaped():
    exp = _expand([root_node(), file_node("F1", FOLDER_ID, "CON.txt")])
    assert exp.files[0].rel_path[-1] == "_CON.txt"


def test_name_collision_gets_a_suffix_and_never_overwrites():
    exp = _expand([
        root_node("R"),
        file_node("F1", FOLDER_ID, "stesso.bin", seed=200),
        file_node("F2", FOLDER_ID, "stesso.bin", seed=300),
        file_node("F3", FOLDER_ID, "stesso.bin", seed=400),
    ])
    paths = _paths(exp)
    assert len(set(paths)) == 3
    assert sorted(paths) == [
        "R/stesso (2).bin", "R/stesso (3).bin", "R/stesso.bin",
    ]


def test_collision_is_case_insensitive_like_windows():
    exp = _expand([
        root_node("R"),
        file_node("F1", FOLDER_ID, "Stesso.BIN", seed=200),
        file_node("F2", FOLDER_ID, "stesso.bin", seed=300),
    ])
    assert len({p.lower() for p in _paths(exp)}) == 2


def test_same_name_in_different_subfolders_does_not_collide():
    exp = _expand([
        root_node("R"),
        folder_node("D1", FOLDER_ID, "a", seed=100),
        folder_node("D2", FOLDER_ID, "b", seed=110),
        file_node("F1", "D1", "x.bin", seed=200),
        file_node("F2", "D2", "x.bin", seed=300),
    ])
    assert sorted(_paths(exp)) == ["R/a/x.bin", "R/b/x.bin"]


def test_undecryptable_node_is_skipped_not_fatal():
    bad = {"h": "FX", "p": FOLDER_ID, "t": 0, "s": 1, "k": "", "a": ""}
    exp = _expand([root_node(), file_node("F1", FOLDER_ID, "ok.bin"), bad])
    assert _paths(exp) == ["Mia Cartella/ok.bin"]
    assert exp.n_skipped == 1


def test_file_without_readable_name_falls_back_to_handle():
    node = file_node("F1", FOLDER_ID, "x.bin")
    node["a"] = ""     # attributi illeggibili, chiave ancora valida
    exp = _expand([root_node(), node])
    assert exp.files[0].rel_path[-1] == "mega_F1"


def test_folder_name_falls_back_when_root_attrs_unreadable():
    exp = _expand([
        {"h": FOLDER_ID, "t": 2},
        file_node("F1", FOLDER_ID, "x.bin"),
    ])
    assert exp.folder_name == f"folder_{FOLDER_ID}"
    assert _paths(exp) == [f"folder_{FOLDER_ID}/x.bin"]


# ---- sotto-selezione (link combinati) --------------------------------------

def test_selected_file_expands_to_that_file_only():
    exp = _expand(
        [
            root_node("R"),
            folder_node("D1", FOLDER_ID, "sub", seed=100),
            file_node("F1", "D1", "voluto.bin", seed=200),
            file_node("F2", FOLDER_ID, "altro.bin", seed=300),
        ],
        sub_kind="file", sub_handle="F1",
    )
    # Il path resta radicato al nome della cartella condivisa.
    assert _paths(exp) == ["R/sub/voluto.bin"]


def test_selected_subfolder_expands_to_its_subtree_only():
    exp = _expand(
        [
            root_node("R"),
            folder_node("D1", FOLDER_ID, "voluta", seed=100),
            folder_node("D2", "D1", "dentro", seed=110),
            folder_node("D3", FOLDER_ID, "esclusa", seed=120),
            file_node("F1", "D1", "a.bin", seed=200),
            file_node("F2", "D2", "b.bin", seed=300),
            file_node("F3", "D3", "c.bin", seed=400),
            file_node("F4", FOLDER_ID, "d.bin", seed=500),
        ],
        sub_kind="folder", sub_handle="D1",
    )
    assert sorted(_paths(exp)) == ["R/voluta/a.bin", "R/voluta/dentro/b.bin"]


def test_legacy_auto_sub_resolves_kind_from_node_type():
    nodes = [
        root_node("R"),
        folder_node("D1", FOLDER_ID, "sub", seed=100),
        file_node("F1", "D1", "a.bin", seed=200),
        file_node("F2", FOLDER_ID, "b.bin", seed=300),
    ]
    as_folder = _expand(nodes, sub_kind="auto", sub_handle="D1")
    as_file = _expand(nodes, sub_kind="auto", sub_handle="F2")
    assert _paths(as_folder) == ["R/sub/a.bin"]
    assert _paths(as_file) == ["R/b.bin"]


def test_unknown_sub_handle_raises():
    with pytest.raises(MegaFolderError):
        _expand([root_node(), file_node("F1", FOLDER_ID, "a.bin")],
                sub_kind="file", sub_handle="NOPE")


# ---- cap e robustezza ------------------------------------------------------

def test_max_files_caps_and_reports_the_excess():
    nodes = [root_node("R")] + [
        file_node(f"F{i}", FOLDER_ID, f"f{i:03d}.bin", seed=200 + i * 10)
        for i in range(10)
    ]
    exp = _expand(nodes, max_files=4)
    assert len(exp.files) == 4
    assert exp.total_files == 10
    assert exp.truncated == 6   # esplicito, non troncamento silenzioso


def test_no_nodes_at_all_raises():
    with pytest.raises(MegaFolderError):
        _expand([])


def test_wrong_master_key_length_raises():
    with pytest.raises(MegaFolderError):
        build_folder_expansion(FOLDER_ID, (1, 2, 3), [root_node()])


def test_parent_cycle_does_not_hang():
    nodes = [
        root_node("R"),
        folder_node("D1", "D2", "a", seed=100),
        folder_node("D2", "D1", "b", seed=110),   # ciclo D1 <-> D2
        file_node("F1", "D1", "x.bin", seed=200),
    ]
    exp = _expand(nodes)   # deve terminare
    assert exp.files[0].rel_path[-1] == "x.bin"


# ---- job auto-contenuti ----------------------------------------------------

def test_job_urls_are_self_contained_and_reparsable():
    exp = _expand([
        root_node("R"),
        folder_node("D1", FOLDER_ID, "sub", seed=100),
        file_node("F1", "D1", "x.bin", seed=200),
    ])
    url = exp.job_urls()[0]
    job = parse_folder_job_url(url)
    assert job is not None
    assert job.folder_id == FOLDER_ID
    assert job.node_handle == "F1"
    assert job.rel_path == ("R", "sub", "x.bin")


def test_job_key_round_trips_to_the_original_file_key():
    from src.downloader.mega_crypto import base64_to_a32

    key = _file_key(200)
    exp = _expand([root_node(), file_node("F1", FOLDER_ID, "x.bin", seed=200)])
    assert base64_to_a32(exp.files[0].key_b64) == key
    # ...e da li' si ricava la coppia (k, iv) per l'AES-CTR del payload.
    assert derive_file_key(base64_to_a32(exp.files[0].key_b64)) == derive_file_key(key)


def test_expansion_is_reproducible_across_runs():
    nodes = [root_node("R")] + [
        file_node(f"F{i}", FOLDER_ID, "stesso.bin", seed=200 + i * 10)
        for i in range(3)
    ]
    assert _expand(nodes).job_urls() == _expand(nodes).job_urls()


# ---- quirk osservati su una cartella pubblica REALE ------------------------
# (link di test lDsUgAAL: 205 file, 21 sottocartelle)

OTHER_MASTER = (0xDEADBEEF, 0xFEEDFACE, 0x12345678, 0x9ABCDEF0)


def _enc_with(plain, master):
    aes = AES.new(a32_to_str(master), AES.MODE_ECB)
    return _b64(aes.encrypt(a32_to_str(plain)))


def multi_key_file_node(handle, parent, name, seed=200, size=111):
    """Nodo il cui campo `k` porta DUE voci: la prima intestata a una share
    diversa (e cifrata con un'altra chiave), la seconda quella buona.

    E' il caso reale: l'owner delle voci di `k` non coincide con l'id della
    cartella nel link, e prendere "la prima" da una chiave sbagliata.
    """
    key = _file_key(seed)
    attr_key, _iv = derive_file_key(key)
    decoy = _enc_with(key, OTHER_MASTER)      # illeggibile con la nostra master
    good = _enc_key(key)
    return {
        "h": handle, "p": parent, "t": 0, "s": size,
        "k": f"ALTRASHARE:{decoy}/INTERNA:{good}",
        "a": _enc_attr(name, attr_key),
    }


def test_picks_the_k_entry_that_actually_decrypts_the_attributes():
    exp = _expand([root_node("R"), multi_key_file_node("F1", FOLDER_ID, "vero.srt")])
    assert _paths(exp) == ["R/vero.srt"]
    assert exp.n_skipped == 0


def test_picked_key_is_the_real_file_key_not_the_decoy():
    from src.downloader.mega_crypto import base64_to_a32

    exp = _expand([root_node("R"), multi_key_file_node("F1", FOLDER_ID, "vero.srt", seed=250)])
    assert base64_to_a32(exp.files[0].key_b64) == _file_key(250)


def test_multi_key_folder_node_name_is_resolved_too():
    key = _folder_key(100)
    node = {
        "h": "D1", "p": FOLDER_ID, "t": 1,
        "k": f"ALTRASHARE:{_enc_with(key, OTHER_MASTER)}/INTERNA:{_enc_key(key)}",
        "a": _enc_attr("Ita S01 S02", key),
    }
    exp = _expand([root_node("R"), node, file_node("F1", "D1", "x.srt", seed=200)])
    assert _paths(exp) == ["R/Ita S01 S02/x.srt"]


def test_file_with_unverifiable_key_is_skipped_not_downloaded_corrupt():
    # Attributi presenti ma nessuna voce di `k` li decifra: la chiave non e'
    # affidabile e scaricare produrrebbe byte corrotti senza alcun errore.
    key = _file_key(200)
    attr_key, _iv = derive_file_key(key)
    node = {
        "h": "F1", "p": FOLDER_ID, "t": 0, "s": 10,
        "k": f"ALTRASHARE:{_enc_with(key, OTHER_MASTER)}",
        "a": _enc_attr("x.bin", attr_key),
    }
    exp = _expand([root_node("R"), node, file_node("F2", FOLDER_ID, "buono.bin", seed=300)])
    assert _paths(exp) == ["R/buono.bin"]
    assert exp.n_skipped == 1


def test_listing_without_a_type_two_root_still_builds_the_tree():
    # Sul campo il nodo `t == 2` puo' mancare del tutto: la radice e' il nodo
    # senza genitore nell'elenco.
    exp = _expand([
        {"h": "ROOTDIR", "p": "FUORI", "t": 1,
         "k": f"{FOLDER_ID}:{_enc_key(_folder_key(50))}",
         "a": _enc_attr("Text Com", _folder_key(50))},
        folder_node("D1", "ROOTDIR", "PGS-sup", seed=100),
        file_node("F1", "D1", "a.sup", seed=200),
    ])
    assert exp.folder_name == "Text Com"
    assert _paths(exp) == ["Text Com/PGS-sup/a.sup"]


def test_root_choice_is_deterministic_when_several_nodes_are_orphans():
    nodes = [
        {"h": "BBB", "p": "FUORI", "t": 1,
         "k": f"{FOLDER_ID}:{_enc_key(_folder_key(50))}",
         "a": _enc_attr("bee", _folder_key(50))},
        {"h": "AAA", "p": "ALTROVE", "t": 1,
         "k": f"{FOLDER_ID}:{_enc_key(_folder_key(60))}",
         "a": _enc_attr("ay", _folder_key(60))},
        file_node("F1", "AAA", "x.bin", seed=200),
    ]
    assert _paths(_expand(nodes)) == _paths(_expand(list(reversed(nodes))))


def test_file_without_attributes_but_one_key_is_kept():
    # Unica chiave candidata: non c'e' niente da scegliere ne' da verificare.
    node = file_node("F1", FOLDER_ID, "x.bin")
    node["a"] = ""
    exp = _expand([root_node("R"), node])
    assert _paths(exp) == ["R/mega_F1"]
    assert exp.n_skipped == 0


def test_file_without_attributes_and_several_keys_is_skipped():
    # Nessun oracolo per verificare E piu' candidate: sceglierne una a caso
    # significherebbe scaricare byte corrotti senza accorgersene.
    key = _file_key(200)
    node = {
        "h": "F1", "p": FOLDER_ID, "t": 0, "s": 10,
        "k": f"{FOLDER_ID}:{_enc_with(key, OTHER_MASTER)}/INTERNA:{_enc_key(key)}",
        "a": "",
    }
    exp = _expand([root_node("R"), node, file_node("F2", FOLDER_ID, "ok.bin", seed=300)])
    assert _paths(exp) == ["R/ok.bin"]
    assert exp.n_skipped == 1


# ---- de-collisione GLOBALE fra cartelle diverse ----------------------------

def _job(folder_id, node, rel):
    from src.core.mega_links import build_folder_job_url
    return build_folder_job_url(folder_id, node, "S2V5OA", rel)


def _rel(url):
    return parse_folder_job_url(url).rel_path


def test_same_node_pasted_twice_is_removed_once():
    a = _job("F1", "N1", ("Cart", "x.bin"))
    out, removed = deduplicate_job_urls([a, a])
    assert out == [a] and removed == 1


def test_two_different_folders_with_the_same_name_get_separate_trees():
    # Due cartelle Mega diverse ma con lo stesso nome e lo stesso file dentro:
    # gli URL sono diversi (node handle diverso), il PATH sarebbe identico.
    # Si separano alla RADICE, non con un suffisso sul nome file: cosi' i due
    # alberi restano distinti invece di mescolarsi in un'unica cartella.
    a = _job("FOLDA", "N1", ("Backup", "foto.jpg"))
    b = _job("FOLDB", "N2", ("Backup", "foto.jpg"))
    out, removed = deduplicate_job_urls([a, b])
    assert removed == 0
    assert _rel(out[0]) == ("Backup", "foto.jpg")
    assert _rel(out[1]) == ("Backup (2)", "foto.jpg")


def test_files_of_the_same_share_stay_in_one_tree():
    a = _job("FOLDA", "N1", ("Backup", "a.jpg"))
    b = _job("FOLDA", "N2", ("Backup", "sub", "b.jpg"))
    c = _job("FOLDB", "N3", ("Backup", "c.jpg"))
    out, _ = deduplicate_job_urls([a, b, c])
    assert _rel(out[0])[0] == _rel(out[1])[0] == "Backup"
    assert _rel(out[2])[0] == "Backup (2)"


def test_a_file_cannot_take_the_name_of_a_sibling_directory():
    # "Eng" come file e "Eng" come cartella nello stesso ramo: su disco uno
    # escluderebbe l'altro. La cartella ha la precedenza, il file si sposta.
    a = _job("F1", "N1", ("R", "Eng"))
    b = _job("F1", "N2", ("R", "Eng", "dentro.sup"))
    out, _ = deduplicate_job_urls([a, b])
    paths = [_rel(u) for u in out]
    assert ("R", "Eng", "dentro.sup") in paths
    assert ("R", "Eng") not in paths          # il file ha ceduto il posto
    assert paths[0] == ("R", "Eng (2)")


def test_collision_across_folders_is_case_insensitive():
    a = _job("FOLDA", "N1", ("Backup", "Foto.JPG"))
    b = _job("FOLDB", "N2", ("backup", "foto.jpg"))
    out, _removed = deduplicate_job_urls([a, b])
    assert len({"/".join(_rel(u)).lower() for u in out}) == 2


def test_single_file_links_pass_through_in_place():
    plain = "https://mega.nz/file/ABC#KEY"
    a = _job("F1", "N1", ("Cart", "x.bin"))
    out, removed = deduplicate_job_urls([plain, a, plain])
    # I link a file singolo NON vengono deduplicati: finiscono in cartelle
    # distinte grazie al suffisso _<file_id>, e i duplicati possono essere voluti.
    assert out == [plain, a, plain] and removed == 0


def test_key_and_handle_survive_the_rewrite():
    from src.core.mega_links import parse_folder_job_url as pj

    a = _job("FOLDA", "N1", ("Backup", "foto.jpg"))
    b = _job("FOLDB", "N2", ("Backup", "foto.jpg"))
    out, _ = deduplicate_job_urls([a, b])
    second = pj(out[1])
    assert (second.folder_id, second.node_handle) == ("FOLDB", "N2")
    assert second.node_key_b64 == pj(b).node_key_b64


def test_collision_suffix_survives_resanitization_at_the_filesystem_boundary():
    from src.core.file_naming import sanitize_file_name

    # STESSA share (stesso folder_id): la de-collisione tocca il nome file, non
    # la radice. Nome gia' al limite di lunghezza: il caso in cui un suffisso
    # accodato senza budget verrebbe ritagliato via, riportando la collisione.
    long_stem = "x" * 250
    a = _job("FOLDA", "N1", ("C", f"{long_stem}.bin"))
    b = _job("FOLDA", "N2", ("C", f"{long_stem}.bin"))
    out, _ = deduplicate_job_urls([a, b])
    names = [_rel(u)[-1] for u in out]
    # I nomi memorizzati devono essere gia' stabili: ri-sanificarli (come fanno
    # worker e _resolve_folder_node prima di toccare il disco) non deve
    # riportarli a collidere.
    assert names[0] != names[1]
    assert [sanitize_file_name(n) for n in names] == names


def test_root_decollision_terminates_on_names_at_the_length_limit():
    # Due share il cui nome, una volta troncato al limite dei segmenti, e'
    # IDENTICO. Accodare ' (n)' senza budget lo farebbe ritagliare via da
    # sanitize_folder_name, che restituirebbe di nuovo il nome base: il ciclo
    # di de-collisione girerebbe all'infinito bloccando il thread.
    base = "S" * 80
    urls = [
        _job(f"FOLD{i}", f"N{i}", (base, "x.bin")) for i in range(4)
    ]
    out, _ = deduplicate_job_urls(urls)
    roots = [_rel(u)[0] for u in out]
    assert len({r.lower() for r in roots}) == 4
    assert all(len(r) <= 80 for r in roots)


def test_file_decollision_terminates_on_names_at_the_length_limit():
    name = "y" * 196 + ".bin"
    urls = [_job("FOLDA", f"N{i}", ("C", name)) for i in range(4)]
    out, _ = deduplicate_job_urls(urls)
    names = [_rel(u)[-1] for u in out]
    assert len({n.lower() for n in names}) == 4
    assert all(len(n) <= 200 for n in names)
