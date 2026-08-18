# Riconoscimento e costruzione dei link pubblici Mega. Fonte di verita' UNICA
# per le forme di URL usate dall'app: file singolo, cartella, cartella con nodo
# selezionato, formati legacy e la forma INTERNA dei job generati espandendo
# una cartella.
#
# Vive in core/ (non in downloader/) per due motivi:
#   1. e' parsing puro: solo stdlib, nessun I/O, nessuna dipendenza da Crypto;
#   2. cosi' anche core/download_history.py puo' riusarlo senza violare la
#      regola "core non importa da src.downloader" (prima duplicava le regex).
from __future__ import annotations

import base64
import re
from dataclasses import dataclass

MEGA_PREFIX = "https://mega.nz/"

# Handle Mega (base64url senza padding) e chiave nel fragment (Mega inserisce
# talvolta virgole nelle chiavi legacy: vanno accettate e scartate dal decoder).
_H = r"[A-Za-z0-9_-]+"
_K = r"[A-Za-z0-9_,-]+"

# ATTENZIONE all'ORDINE di applicazione (dal piu' specifico al piu' generico):
# la forma interna dei job contiene sia "/folder/" sia "/file/" e verrebbe
# catturata dalle regex generiche se testata per ultima.
#
# Forma INTERNA (auto-contenuta) prodotta dall'espansione di una cartella:
#   https://mega.nz/folder/<folder_id>/file/<node>?p=<b64url(rel_path)>#<key8w>
# Il "?p=" prima del fragment e' voluto: impedisce a _FILE_RE (che richiede '#'
# subito dopo l'handle) di scambiarla per un normale link a file singolo.
_FOLDER_JOB_RE = re.compile(
    rf"/folder/({_H})/file/({_H})\?p=({_H})(?:&s=(\d+))?#({_K})"
)
# Cartella con un FILE selezionato: /folder/<id>#<key>/file/<node>
_FOLDER_FILE_RE = re.compile(rf"/folder/({_H})#({_K})/file/({_H})")
# Cartella con una SOTTOCARTELLA selezionata: /folder/<id>#<key>/folder/<node>
_FOLDER_SUB_RE = re.compile(rf"/folder/({_H})#({_K})/folder/({_H})")
# Cartella intera: /folder/<id>#<key>
_FOLDER_RE = re.compile(rf"/folder/({_H})#({_K})")
# Cartella legacy: #F!<id>!<key> con terzo campo opzionale (file O sottocartella:
# il formato non lo distingue, lo risolviamo dal tipo del nodo in fase di listing).
_LEGACY_FOLDER_RE = re.compile(rf"#F!({_H})!({_K})(?:!({_H}))?")
# File singolo: /file/<handle>#<key>
_FILE_RE = re.compile(rf"/file/({_H})#({_K})")
# File singolo legacy: #!<handle>!<key>
_LEGACY_FILE_RE = re.compile(rf"#!({_H})!({_K})")
# Variante "senza chiave" usata SOLO da extract_handle (dedup storico): a noi
# basta l'handle, la chiave puo' mancare.
_FILE_HANDLE_ONLY_RE = re.compile(rf"/file/({_H})")

# Tipi di sotto-selezione dentro un link cartella.
SUB_FILE = "file"
SUB_FOLDER = "folder"
SUB_AUTO = "auto"  # legacy: il tipo si scopre dal nodo


@dataclass(frozen=True)
class MegaFileLink:
    """Link pubblico a un file singolo (nuovo formato o legacy)."""

    handle: str
    key_b64: str


@dataclass(frozen=True)
class MegaFolderLink:
    """Link pubblico a una cartella, eventualmente con un nodo selezionato."""

    folder_id: str
    key_b64: str
    sub_kind: str | None = None   # SUB_FILE / SUB_FOLDER / SUB_AUTO / None
    sub_handle: str | None = None


@dataclass(frozen=True)
class MegaFolderJobLink:
    """Forma INTERNA di un job generato espandendo una cartella.

    Auto-contenuta: porta tutto cio' che serve a risolversi da sola su un
    proxy qualunque, a ogni retry, senza ri-elencare la cartella.
    `rel_path` include il nome file come ultimo segmento.
    """

    folder_id: str
    node_handle: str
    node_key_b64: str            # chiave file a 8 word, base64url
    rel_path: tuple[str, ...]
    # Dimensione attesa in byte, nota gia' dall'elenco della cartella. Serve al
    # worker per distinguere "il MIO file e' gia' completo" da "esiste un file
    # omonimo di un'altra origine": nell'albero il path e' stabile, quindi il
    # solo nome non basta a stabilire la proprieta'. None = job vecchio stile.
    size: int | None = None

    @property
    def file_name(self) -> str:
        return self.rel_path[-1] if self.rel_path else ""


def _b64url_encode(text: str) -> str:
    """base64url SENZA padding: resta nel charset degli handle Mega."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def build_folder_job_url(
    folder_id: str,
    node_handle: str,
    node_key_b64: str,
    rel_path: tuple[str, ...],
    size: int | None = None,
) -> str:
    """Costruisce la forma interna di un job-cartella (inverso di parse_folder_job_url)."""
    if not folder_id or not node_handle or not node_key_b64:
        raise ValueError("folder_id, node_handle e node_key_b64 sono obbligatori")
    if not rel_path:
        raise ValueError("rel_path non puo' essere vuoto")
    packed = _b64url_encode("/".join(rel_path))
    size_part = f"&s={int(size)}" if size is not None and int(size) >= 0 else ""
    return (
        f"{MEGA_PREFIX}folder/{folder_id}/file/{node_handle}"
        f"?p={packed}{size_part}#{node_key_b64}"
    )


def parse_folder_job_url(url: str) -> MegaFolderJobLink | None:
    """Ritorna il job-cartella se `url` e' nella forma interna, altrimenti None."""
    if not url:
        return None
    m = _FOLDER_JOB_RE.search(url)
    if not m:
        return None
    try:
        rel = _b64url_decode(m.group(3))
    except (ValueError, UnicodeDecodeError):
        return None
    segments = tuple(s for s in rel.split("/") if s)
    if not segments:
        return None
    raw_size = m.group(4)
    return MegaFolderJobLink(
        folder_id=m.group(1),
        node_handle=m.group(2),
        node_key_b64=m.group(5),
        rel_path=segments,
        size=int(raw_size) if raw_size is not None else None,
    )


def parse_folder_link(url: str) -> MegaFolderLink | None:
    """Ritorna il link-cartella (con eventuale nodo selezionato) o None.

    NON matcha la forma interna dei job: quelli sono gia' file espansi.
    """
    if not url or parse_folder_job_url(url) is not None:
        return None
    m = _FOLDER_FILE_RE.search(url)
    if m:
        return MegaFolderLink(m.group(1), m.group(2), SUB_FILE, m.group(3))
    m = _FOLDER_SUB_RE.search(url)
    if m:
        return MegaFolderLink(m.group(1), m.group(2), SUB_FOLDER, m.group(3))
    m = _FOLDER_RE.search(url)
    if m:
        return MegaFolderLink(m.group(1), m.group(2))
    m = _LEGACY_FOLDER_RE.search(url)
    if m:
        sub = m.group(3)
        # Il formato legacy non dice se il terzo campo e' un file o una
        # sottocartella: lo decide il tipo del nodo in fase di listing.
        return MegaFolderLink(
            m.group(1), m.group(2), SUB_AUTO if sub else None, sub,
        )
    return None


def parse_file_link(url: str) -> MegaFileLink | None:
    """Ritorna il link a file singolo (nuovo o legacy) o None.

    Esclude esplicitamente le forme cartella: un link combinato
    `/folder/<id>#<key>/file/<node>` NON e' risolvibile come file pubblico.
    """
    if not url or parse_folder_job_url(url) is not None:
        return None
    if parse_folder_link(url) is not None:
        return None
    m = _FILE_RE.search(url)
    if m:
        return MegaFileLink(m.group(1), m.group(2))
    m = _LEGACY_FILE_RE.search(url)
    if m:
        return MegaFileLink(m.group(1), m.group(2))
    return None


def is_folder_link(url: str) -> bool:
    """True solo per i link cartella da espandere (non per i job gia' espansi)."""
    return parse_folder_link(url) is not None


def extract_handle(url: str) -> str | None:
    """Estrae l'handle del FILE da un link Mega, senza rete.

    Ritorna None per i link cartella non ancora espansi (niente handle di file
    da confrontare con lo storico) e per tutto cio' che non e' riconosciuto.
    Per la forma interna dei job ritorna l'handle del NODO: il dedup storico
    resta quindi per-file anche dentro le cartelle.
    """
    if not url:
        return None
    job = parse_folder_job_url(url)
    if job is not None:
        return job.node_handle
    folder = parse_folder_link(url)
    if folder is not None:
        # Solo un nodo esplicitamente marcato come file ha un handle di file.
        return folder.sub_handle if folder.sub_kind == SUB_FILE else None
    m = _FILE_HANDLE_ONLY_RE.search(url)
    if m:
        return m.group(1)
    m = _LEGACY_FILE_RE.search(url)
    if m:
        return m.group(1)
    return None
