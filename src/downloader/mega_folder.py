# Espansione di un link cartella Mega in N job-file AUTO-CONTENUTI.
#
# Principio (relazione tecnica, F3): NON esiste un secondo motore di download.
# La cartella viene elencata UNA SOLA volta, ogni file diventa un job che porta
# con se' tutto il necessario a risolversi da solo (folder_id + handle del nodo
# + chiave a 8 word gia' decifrata + path relativo). Da li' in poi scorre nel
# motore esistente: worker, rotazione proxy, coda di chunk, resume .part,
# storico, ripristino sessione.
#
# Perche' auto-contenuti: il motore ri-risolve la URL CDN a ogni tentativo, su
# proxy diversi e su piu' worker. Ri-elencare la cartella a ogni retry
# moltiplicherebbe le chiamate API (rate-limit) e imporrebbe una cache
# condivisa fra thread. Un job-cartella e' self-describing esattamente come lo
# e' gia' oggi un link a file singolo.
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Callable

from src.core.config import MEGA_FOLDER_LIST_TIMEOUT, MEGA_FOLDER_MAX_FILES
from src.core.file_naming import (
    MAX_FILE_NAME_LEN,
    sanitize_file_name,
    sanitize_folder_name,
)
from src.core.mega_links import (
    SUB_AUTO,
    MegaFolderJobLink,
    SUB_FILE,
    SUB_FOLDER,
    MegaFolderLink,
    build_folder_job_url,
    parse_folder_job_url,
    parse_folder_link,
)
from src.downloader.mega_api import MegaApiError, MegaPublicClient
from src.downloader.mega_crypto import (
    a32_to_str,
    base64_to_a32,
    base64_url_decode,
    decrypt_attr,
    decrypt_key,
    derive_file_key,
)

log = logging.getLogger(__name__)

# Tipi di nodo nella risposta `f` dell'API Mega.
NODE_FILE = 0
NODE_FOLDER = 1
NODE_ROOT = 2

# Guardia contro catene di genitori cicliche/corrotte in una risposta ostile.
_MAX_TREE_DEPTH = 32
# I segmenti di cartella dentro un albero sono piu' corti del solito: un path
# annidato deve restare sotto i limiti di lunghezza di Windows.
_TREE_SEGMENT_MAX_LEN = 80


class MegaFolderError(MegaApiError):
    """Errore specifico dell'espansione di una cartella."""


@dataclass(frozen=True)
class FolderFile:
    """Un file dentro una cartella condivisa, pronto a diventare un job."""

    node_handle: str
    key_b64: str                  # chiave a 8 word, base64url senza padding
    size: int
    rel_path: tuple[str, ...]     # segmenti sanificati, ultimo = nome file


@dataclass(frozen=True)
class FolderExpansion:
    """Esito dell'espansione di un link cartella."""

    folder_id: str
    folder_name: str
    files: tuple[FolderFile, ...]
    total_files: int              # file trovati PRIMA del cap
    n_folders: int
    n_skipped: int                # nodi non decifrabili / ignorati

    @property
    def truncated(self) -> int:
        return max(0, self.total_files - len(self.files))

    def job_urls(self) -> list[str]:
        return [
            build_folder_job_url(
                self.folder_id, f.node_handle, f.key_b64, f.rel_path, f.size,
            )
            for f in self.files
        ]


def _a32_to_b64(key: tuple[int, ...]) -> str:
    """a32 -> base64url senza padding (formato usato nei job)."""
    return base64.urlsafe_b64encode(a32_to_str(key)).decode("ascii").rstrip("=")


def _key_candidates(
    k_field: object, folder_id: str, master: tuple[int, ...],
) -> list[tuple[int, ...]]:
    """Tutte le chiavi plausibili di un nodo, in ordine di preferenza.

    Il campo `k` puo' contenere PIU' voci `<owner>:<blob>` separate da `/`, e
    l'owner NON coincide necessariamente con l'id della cartella nella URL:
    sul campo si osservano share con un handle interno diverso da quello del
    link (es. link a `lDsUgAAL`, voci intestate a `dX0EFDoK`). Prendere "la
    prima" o "quella che combacia col folder_id" sbaglia. Si generano quindi
    tutti i candidati e la scelta la fa la validazione degli attributi.
    """
    if not isinstance(k_field, str) or not k_field:
        return []
    preferred: list[tuple[int, ...]] = []
    others: list[tuple[int, ...]] = []
    for part in k_field.split("/"):
        owner, sep, blob = part.partition(":")
        if not sep or not blob:
            continue
        try:
            key = decrypt_key(base64_to_a32(blob), master)
        except (ValueError, TypeError) as exc:
            log.debug("[mega_folder] voce di k non decifrabile (%s): %s", blob, exc)
            continue
        (preferred if owner == folder_id else others).append(key)
    return preferred + others


def _attr_key(node_key: tuple[int, ...] | None) -> tuple[int, ...] | None:
    """Chiave con cui si decifrano gli ATTRIBUTI di un nodo.

    Per un file e' la meta' XOR-ata della chiave a 8 word (la stessa `k` che
    poi cifra il payload); per una cartella e' la chiave stessa.
    """
    if node_key is None:
        return None
    if len(node_key) >= 8:
        return derive_file_key(node_key)[0]
    if len(node_key) == 4:
        return node_key
    return None


def _decode_attr_blob(node: dict) -> bytes | None:
    raw_attr = node.get("a")
    if not isinstance(raw_attr, str) or not raw_attr:
        return None
    try:
        return base64_url_decode(raw_attr)
    except (ValueError, TypeError):
        return None


def _read_name(blob: bytes, key: tuple[int, ...] | None) -> str | None:
    if key is None or len(key) != 4:
        return None
    attrs = decrypt_attr(blob, key)
    if not attrs:
        return None
    name = attrs.get("n")
    return name if isinstance(name, str) and name.strip() else None


def _node_key_and_name(
    node: dict, folder_id: str, master: tuple[int, ...],
) -> tuple[tuple[int, ...] | None, str | None, bool]:
    """(chiave, nome, chiave_verificata) di un nodo.

    La chiave giusta si riconosce da se': `decrypt_attr` controlla il magic
    `MEGA{"` e fallisce su una chiave sbagliata. Si provano quindi tutti i
    candidati e si tiene quello i cui attributi si decifrano — l'unico modo
    affidabile quando `k` porta piu' voci intestate a share diverse.

    Il terzo valore dice se la chiave e' AFFIDABILE: o perche' verificata sugli
    attributi, o perche' era l'unica candidata possibile e non c'era nulla da
    scegliere. Un file la cui chiave e' solo indovinata fra piu' candidate va
    scartato, non scaricato in silenzio con una chiave sbagliata (produrrebbe
    byte corrotti dopo l'AES-CTR, senza alcun errore visibile).
    """
    candidates = _key_candidates(node.get("k"), folder_id, master)
    blob = _decode_attr_blob(node)
    if blob is not None:
        for key in candidates:
            name = _read_name(blob, _attr_key(key))
            if name is not None:
                return key, name, True
        # Nodo radice di una share: attributi cifrati con la master key e
        # nessun `k` proprio da verificare.
        name = _read_name(blob, master)
        if name is not None:
            return (candidates[0] if candidates else None), name, not candidates
    first = candidates[0] if candidates else None
    # Nessun attributo utilizzabile come oracolo. Con UNA sola chiave candidata
    # non c'e' niente da scegliere (e nemmeno come verificare): si accetta, come
    # gia' fa il resolve di un file pubblico singolo quando `at` non si decifra.
    # Con PIU' candidate staremmo invece tirando a indovinare: meglio scartare.
    return first, None, blob is None and len(candidates) == 1


def _resolve_root(nodes: list[dict], folder_id: str) -> str | None:
    """Handle del nodo radice della share.

    `t == 2` e' il caso da manuale ma NON e' garantito: su una cartella
    pubblica reale l'elenco puo' contenere solo nodi `t in (0, 1)`. Si scende
    quindi per fallback: tipo 2 -> handle uguale all'id del link -> nodo senza
    genitore nell'elenco (preferendo una cartella, e in modo deterministico).
    """
    for node in nodes:
        if node.get("t") == NODE_ROOT and isinstance(node.get("h"), str):
            return node["h"]
    handles = {n.get("h") for n in nodes}
    if folder_id in handles:
        return folder_id
    orphans = [
        n["h"] for n in nodes
        if isinstance(n.get("h"), str) and n.get("p") not in handles
    ]
    if not orphans:
        return None
    by_handle = {n["h"]: n for n in nodes if isinstance(n.get("h"), str)}
    folders = sorted(h for h in orphans if by_handle[h].get("t") != NODE_FILE)
    if len(orphans) > 1:
        log.warning(
            "[mega_folder] %d nodi senza genitore nell'elenco: uso %s come radice",
            len(orphans), (folders or sorted(orphans))[0],
        )
    return (folders or sorted(orphans))[0]


def _dedup_paths(paths: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Rende univoci i path collidenti aggiungendo un suffisso ` (n)`.

    Il confronto e' case-insensitive perche' Windows lo e': due nomi che
    differiscono solo per maiuscole sono lo STESSO file su disco.
    """
    # Normalizza OGNI segmento PRIMA di confrontarlo: deduplicate_job_urls puo'
    # ricevere job costruiti altrove, e confrontare nomi che il filesystem
    # accorcerebbe piu' avanti darebbe una falsa unicita'. Sanificando qui, la
    # chiave di dedup coincide con il path che finira' davvero su disco
    # (folder_job_output_dir ri-sanifica con le stesse funzioni).
    paths = [
        tuple(sanitize_folder_name(seg) for seg in p[:-1])
        + (sanitize_file_name(p[-1]),)
        for p in paths
    ]
    # Un file non puo' chiamarsi come una CARTELLA sorella: su disco l'uno
    # escluderebbe l'altra (mkdir fallirebbe, o la scrittura del file). I path
    # di cartella hanno la precedenza; il file collidente prende un suffisso.
    dir_keys = {
        "/".join(p[:i]).lower()
        for p in paths
        for i in range(1, len(p))
    }
    seen: set[str] = set()
    out: list[tuple[str, ...]] = []
    for path in paths:
        key = "/".join(path).lower()
        if key not in seen and key not in dir_keys:
            seen.add(key)
            out.append(path)
            continue
        head, name = path[:-1], path[-1]
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        n = 2
        while True:
            candidate = _suffixed_name(stem, dot, ext, n)
            new_path = head + (candidate,)
            new_key = "/".join(new_path).lower()
            if new_key not in seen and new_key not in dir_keys:
                seen.add(new_key)
                out.append(new_path)
                log.warning(
                    "[mega_folder] collisione di nome in %s: '%s' -> '%s'",
                    "/".join(head) or ".", name, candidate,
                )
                break
            n += 1
    return out


def _suffixed_name(stem: str, dot: str, ext: str, n: int) -> str:
    """Nome de-collisionato `<stem> (n).<ext>` STABILE alla ri-sanificazione.

    Il gambo viene accorciato per fare posto al suffisso PRIMA di comporre il
    nome: se ci si limitasse ad accodare ' (n)', su un nome gia' al limite di
    lunghezza sarebbe `sanitize_file_name` a ritagliare via proprio il suffisso
    (worker e `_resolve_folder_node` ri-sanificano prima di toccare il disco),
    riportando il nome a collidere — e il ciclo di de-collisione non
    terminerebbe mai, perche' ogni n produrrebbe lo stesso nome troncato.
    """
    suffix = f" ({n})"
    budget = MAX_FILE_NAME_LEN - len(suffix) - len(dot) - len(ext)
    trimmed = stem[:budget].rstrip() if budget > 0 else ""
    return sanitize_file_name(
        f"{trimmed}{suffix}{dot}{ext}", fallback=f"download{suffix}{dot}{ext}",
    )


def build_folder_expansion(
    folder_id: str,
    master: tuple[int, ...],
    nodes: list[dict],
    sub_kind: str | None = None,
    sub_handle: str | None = None,
    max_files: int = MEGA_FOLDER_MAX_FILES,
) -> FolderExpansion:
    """Ricostruisce l'albero della cartella e produce i file da scaricare.

    Funzione PURA rispetto alla rete: riceve i nodi gia' scaricati e fa solo
    decifratura + ricostruzione dei path. `sub_*` filtra quali file includere
    (link combinato `/folder/#key/file|folder/<node>`) ma NON cambia i path: il
    path relativo e' SEMPRE radicato al nome della cartella condivisa, cosi'
    l'albero su disco e' identico qualunque sia il punto di ingresso.
    """
    if len(master) != 4:
        raise MegaFolderError("folder_key_invalid", words=len(master))
    if not nodes:
        raise MegaFolderError("folder_no_nodes")

    by_handle = {n["h"]: n for n in nodes if isinstance(n.get("h"), str)}
    root_handle = _resolve_root(nodes, folder_id)
    if root_handle is None:
        raise MegaFolderError("folder_root_not_found")

    keys: dict[str, tuple[int, ...] | None] = {}
    names: dict[str, str | None] = {}
    verified: dict[str, bool] = {}
    for handle, node in by_handle.items():
        key, name, ok = _node_key_and_name(node, folder_id, master)
        keys[handle] = key
        names[handle] = name
        verified[handle] = ok

    folder_name = names.get(root_handle) or f"folder_{folder_id}"

    # Insieme dei nodi da includere quando il link seleziona un sotto-albero.
    allowed: set[str] | None = None
    kind = sub_kind
    if sub_handle:
        if sub_handle not in by_handle:
            raise MegaFolderError(
                "folder_node_not_in_folder", node=sub_handle
            )
        if kind == SUB_AUTO:
            kind = (
                SUB_FILE
                if by_handle[sub_handle].get("t") == NODE_FILE
                else SUB_FOLDER
            )
        if kind == SUB_FILE:
            allowed = {sub_handle}
        elif kind == SUB_FOLDER:
            allowed = _descendants(by_handle, sub_handle)

    n_folders = 0
    n_skipped = 0
    raw: list[tuple[FolderFile, tuple[str, ...]]] = []
    for handle, node in by_handle.items():
        node_type = node.get("t")
        if node_type == NODE_FOLDER:
            n_folders += 1
            continue
        if node_type != NODE_FILE:
            continue
        if allowed is not None and handle not in allowed:
            continue
        key = keys.get(handle)
        if key is None or len(key) < 8:
            log.warning(
                "[mega_folder] nodo %s senza chiave decifrabile: saltato", handle,
            )
            n_skipped += 1
            continue
        if not verified.get(handle, False):
            # La chiave non ha superato la verifica sugli attributi: scaricare
            # con una chiave sbagliata darebbe byte corrotti dopo l'AES-CTR,
            # senza alcun errore visibile. Meglio saltare e dirlo.
            log.warning(
                "[mega_folder] nodo %s: chiave non verificabile sugli attributi, "
                "saltato per non scaricare dati corrotti", handle,
            )
            n_skipped += 1
            continue
        chain = _path_segments(by_handle, names, handle, root_handle, folder_name)
        try:
            size = int(node.get("s", 0))
        except (TypeError, ValueError):
            size = 0
        raw.append((
            FolderFile(
                node_handle=handle,
                key_b64=_a32_to_b64(tuple(key[:8])),
                size=max(0, size),
                rel_path=(),  # riempito dopo sanificazione + dedup
            ),
            chain,
        ))

    # Ordine deterministico: due espansioni della stessa cartella devono dare
    # gli stessi path (anche i suffissi di de-collisione).
    raw.sort(key=lambda item: ("/".join(item[1]).lower(), item[0].node_handle))
    sanitized = [_sanitize_path(chain, item.node_handle) for item, chain in raw]
    deduped = _dedup_paths(sanitized)

    files = tuple(
        FolderFile(f.node_handle, f.key_b64, f.size, path)
        for (f, _chain), path in zip(raw, deduped)
    )
    total = len(files)
    if max_files > 0 and total > max_files:
        log.warning(
            "[mega_folder] cartella con %d file: limitata ai primi %d "
            "(MEGA_FOLDER_MAX_FILES). %d file NON verranno scaricati.",
            total, max_files, total - max_files,
        )
        files = files[:max_files]

    return FolderExpansion(
        folder_id=folder_id,
        folder_name=sanitize_folder_name(folder_name, _TREE_SEGMENT_MAX_LEN),
        files=files,
        total_files=total,
        n_folders=n_folders,
        n_skipped=n_skipped,
    )


def _descendants(by_handle: dict[str, dict], root: str) -> set[str]:
    """Tutti i nodi (inclusa la radice) del sotto-albero che parte da `root`."""
    children: dict[str, list[str]] = {}
    for handle, node in by_handle.items():
        parent = node.get("p")
        if isinstance(parent, str):
            children.setdefault(parent, []).append(handle)
    out: set[str] = {root}
    stack = [root]
    while stack:
        current = stack.pop()
        for child in children.get(current, ()):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def _path_segments(
    by_handle: dict[str, dict],
    names: dict[str, str | None],
    handle: str,
    root_handle: str,
    folder_name: str,
) -> tuple[str, ...]:
    """Path GREZZO (non sanificato) di un file, dal nome della share al file."""
    chain: list[str] = [names.get(handle) or f"mega_{handle}"]
    current = by_handle[handle].get("p")
    seen = {handle}
    depth = 0
    while (
        isinstance(current, str)
        and current != root_handle
        and current in by_handle
        and current not in seen
        and depth < _MAX_TREE_DEPTH
    ):
        seen.add(current)
        chain.append(names.get(current) or f"cartella_{current}")
        current = by_handle[current].get("p")
        depth += 1
    if depth >= _MAX_TREE_DEPTH:
        log.warning(
            "[mega_folder] catena di genitori troppo profonda per %s: troncata",
            handle,
        )
    chain.append(folder_name)
    chain.reverse()
    return tuple(chain)


def _sanitize_path(chain: tuple[str, ...], node_handle: str) -> tuple[str, ...]:
    """Sanifica ogni segmento: cartelle con sanitize_folder_name, file con
    sanitize_file_name (che preserva l'estensione e blocca i device name)."""
    dirs = tuple(
        sanitize_folder_name(seg, _TREE_SEGMENT_MAX_LEN) for seg in chain[:-1]
    )
    name = sanitize_file_name(chain[-1], fallback=f"mega_{node_handle}")
    return dirs + (name,)


def _suffixed_folder_name(base: str, n: int) -> str:
    """`<base> (n)` per una cartella, STABILE alla troncatura di lunghezza.

    Stessa trappola di _suffixed_name sui file: accodare ' (n)' a un nome gia'
    al limite lo farebbe ritagliare via da sanitize_folder_name, che
    restituirebbe di nuovo `base` — e il ciclo di de-collisione girerebbe
    all'infinito bloccando il thread di espansione. Il gambo si accorcia PRIMA.
    """
    suffix = f" ({n})"
    budget = _TREE_SEGMENT_MAX_LEN - len(suffix)
    trimmed = base[:budget].rstrip() if budget > 0 else ""
    return sanitize_folder_name(f"{trimmed}{suffix}", _TREE_SEGMENT_MAX_LEN)


def _unique_root_names(jobs: "list[MegaFolderJobLink]") -> dict[str, str]:
    """Un nome di cartella top-level distinto per ogni share (`folder_id`).

    Due cartelle Mega DIVERSE possono chiamarsi allo stesso modo: senza questo,
    i loro alberi si fonderebbero in un'unica cartella su disco, mescolando i
    file di origini diverse. La seconda share prende `<nome> (2)`, e cosi' via.
    L'assegnazione segue l'ordine dei job, quindi e' deterministica.
    """
    assigned: dict[str, str] = {}
    used: set[str] = set()
    for job in jobs:
        if job.folder_id in assigned or len(job.rel_path) < 2:
            continue
        base = job.rel_path[0]
        name = base
        n = 2
        while name.lower() in used:
            name = _suffixed_folder_name(base, n)
            n += 1
        if name != base:
            log.warning(
                "[mega_folder] due cartelle Mega si chiamano '%s': la share %s "
                "va in '%s'", base, job.folder_id, name,
            )
        used.add(name.lower())
        assigned[job.folder_id] = name
    return assigned


def deduplicate_job_urls(urls: list[str]) -> tuple[list[str], int]:
    """Rende univoca la DESTINAZIONE su disco di un insieme di job-cartella.

    `build_folder_expansion` de-colliziona i path dentro UNA cartella, ma due
    cartelle diverse possono avere lo stesso nome e contenere lo stesso file:
    i due job avrebbero URL diverse (node handle diverso) e path identico, e
    due worker scriverebbero lo stesso file. Qui si guarda l'insieme completo.

    Ritorna (lista con i path resi univoci, numero di doppioni ESATTI rimossi).
    Un doppione esatto e' lo stesso nodo della stessa cartella (es. lo stesso
    link incollato due volte): si scarta, non si duplica il download. I link
    che non sono job-cartella passano invariati e mantengono la loro posizione.
    """
    seen_nodes: set[tuple[str, str]] = set()
    items: list[str | MegaFolderJobLink] = []
    removed = 0
    for url in urls:
        job = parse_folder_job_url(url)
        if job is None:
            items.append(url)
            continue
        node_id = (job.folder_id, job.node_handle)
        if node_id in seen_nodes:
            removed += 1
            continue
        seen_nodes.add(node_id)
        items.append(job)

    jobs = [it for it in items if isinstance(it, MegaFolderJobLink)]
    roots = _unique_root_names(jobs)
    rel_paths = [
        ((roots[j.folder_id],) + j.rel_path[1:]) if len(j.rel_path) > 1 else j.rel_path
        for j in jobs
    ]
    fixed = iter(_dedup_paths(rel_paths))
    out: list[str] = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        else:
            out.append(
                build_folder_job_url(
                    it.folder_id, it.node_handle, it.node_key_b64, next(fixed),
                    it.size,
                )
            )
    return out, removed


def expand_folder_link(
    url: str,
    proxy: dict | None = None,
    should_abort: Callable[[], bool] | None = None,
    max_files: int = MEGA_FOLDER_MAX_FILES,
    timeout: float = MEGA_FOLDER_LIST_TIMEOUT,
) -> FolderExpansion:
    """Elenca una cartella Mega pubblica e la espande in file scaricabili.

    UNA sola chiamata API per cartella. `proxy=None` = connessione diretta:
    all'avvio della sessione il pool proxy non esiste ancora, e l'elenco nodi
    non e' soggetto al rate-limit per-IP del CDN (che colpisce i download).
    Il parametro resta esposto per instradarla su proxy in futuro.
    """
    link: MegaFolderLink | None = parse_folder_link(url)
    if link is None:
        raise MegaFolderError("not_a_folder_link", url=url)
    try:
        master = base64_to_a32(link.key_b64)
    except (ValueError, TypeError) as exc:
        raise MegaFolderError("folder_key_unreadable", error=str(exc)) from exc
    if len(master) < 4:
        raise MegaFolderError("folder_key_too_short", words=len(master))
    client = MegaPublicClient(proxy, timeout=timeout, should_abort=should_abort)
    nodes = client.list_folder(link.folder_id)
    expansion = build_folder_expansion(
        folder_id=link.folder_id,
        master=tuple(master[:4]),
        nodes=nodes,
        sub_kind=link.sub_kind,
        sub_handle=link.sub_handle,
        max_files=max_files,
    )
    log.info(
        "[mega_folder] '%s' (%s): %d file, %d cartelle, %d nodi saltati",
        expansion.folder_name, link.folder_id, expansion.total_files,
        expansion.n_folders, expansion.n_skipped,
    )
    return expansion
