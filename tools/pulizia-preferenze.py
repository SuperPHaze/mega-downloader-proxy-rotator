"""Reset stato utente del tool per un test da capo.

Cancella:
  - preferences.json      (lingua, tema, cartella download)
  - session_state.json    (sessione da ripristinare al riavvio)
  - branding_cache.json   (cache branding remoto)
  - proxy_cache.json      (cache proxy validati)
  - logs/download_history.log (storico dei download completati)
  - contenuto di downloads/  (i file scaricati)

NON tocca:
  - il codice
  - i log applicativi (app.log*, terminal-log.txt, events.jsonl*)
  - la telemetria (logs/telemetry/)
  - MyDocs/, .git/, altri file utili al debug

Sicuro per la versione in sviluppo, che non e' usata attivamente per
download reali (i download veri stanno su un'altra installazione).

Uso:
    python tools/pulizia-preferenze.py            # chiede conferma
    python tools/pulizia-preferenze.py --yes       # senza chiedere
    python tools/pulizia-preferenze.py --dry-run   # mostra cosa farebbe, non tocca
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

FILES_TO_DELETE = [
    REPO_ROOT / "preferences.json",
    REPO_ROOT / "session_state.json",
    REPO_ROOT / "branding_cache.json",
    REPO_ROOT / "proxy_cache.json",
    REPO_ROOT / "logs" / "download_history.log",
]

# Cartelle da SVUOTARE (contenuto cancellato, cartella stessa preservata:
# alcuni componenti del tool si aspettano che esistano).
DIRS_TO_EMPTY = [
    REPO_ROOT / "downloads",
]


def _print_group(label: str, items: list) -> None:
    if not items:
        return
    print(f"{label} ({len(items)}):")
    for p in items:
        print(f"  - {p.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reset stato utente del tool (preferenze, cache, cartella download).",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="non chiedere conferma")
    parser.add_argument("--dry-run", action="store_true", help="mostra cosa farebbe, senza cancellare")
    args = parser.parse_args(argv)

    files_present = [p for p in FILES_TO_DELETE if p.exists()]
    dirs_with_content = [d for d in DIRS_TO_EMPTY if d.exists() and any(d.iterdir())]

    if not files_present and not dirs_with_content:
        print("Nulla da pulire — lo stato utente e' gia' fresco.")
        return 0

    _print_group("File da cancellare", files_present)
    _print_group("Cartelle da svuotare", dirs_with_content)

    if args.dry_run:
        print("\n(dry-run: nulla e' stato toccato)")
        return 0

    if not args.yes:
        try:
            resp = input("\nProcedere? [s/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in {"s", "si", "si'", "y", "yes"}:
            print("Annullato.")
            return 1

    for p in files_present:
        p.unlink()

    for d in dirs_with_content:
        for child in d.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    print("\nStato utente ripulito.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
