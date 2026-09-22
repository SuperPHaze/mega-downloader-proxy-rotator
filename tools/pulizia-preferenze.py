"""Reset stato utente del tool per un test da capo.

Cancella:
  - preferences.json      (lingua, tema, cartella download)
  - session_state.json    (sessione da ripristinare al riavvio)
  - branding_cache.json   (cache branding remoto)
  - proxy_cache.json      (cache proxy validati)
  - logs/download_history.log (storico dei download completati, archivi inclusi)
  - contenuto di downloads/  (i file scaricati)

NON tocca:
  - il codice
  - i log applicativi (app.log*, terminal-log.txt, events.jsonl*)
  - la telemetria (logs/telemetry/)
  - MyDocs/, .git/, altri file utili al debug

Sicuro per la versione in sviluppo, che non e' usata attivamente per
download reali (i download veri stanno su un'altra installazione).

**Quello che si puo' fare anche dalla GUI**: da Impostazioni -> Manutenzione si
azzerano storico, stato della sessione, cartella dei download, log e cache dei
proxy, con l'elenco di cio' che sparisce e una conferma. Questo script resta
per le due voci che la GUI NON tocca di proposito — `preferences.json` (l'app
le tiene in memoria e le riscriverebbe) e `branding_cache.json` — e per l'uso
non interattivo.

La logica di misura e cancellazione e' UNA sola e vive in
`src/core/maintenance.py`: qui si compone l'elenco, non si riscrive il come.

Uso (dalla root del progetto):
    python tools/pulizia-preferenze.py            # chiede conferma
    python tools/pulizia-preferenze.py --yes       # senza chiedere
    python tools/pulizia-preferenze.py --dry-run   # mostra cosa farebbe, non tocca
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Lanciato come `python tools/pulizia-preferenze.py`, sys.path[0] e' `tools/`:
# senza questa riga l'import di `src.core` non trova niente. E' il prezzo di
# essere uno script a doppio clic invece di un `-m`.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import maintenance                                # noqa: E402
from src.proxy.proxy_cache import cache_path                    # noqa: E402

# File che solo QUESTO strumento cancella: la GUI li lascia stare di proposito
# (`preferences.json` e' tenuto in memoria dall'app e verrebbe riscritto).
EXTRA_FILES = [
    REPO_ROOT / "preferences.json",
    REPO_ROOT / "branding_cache.json",
]

# Voci condivise con la finestra Manutenzione della GUI: stessi percorsi,
# stessa cancellazione. I log applicativi NON sono in elenco: questo strumento
# serve a ripartire da capo con un test, e i log di quel test si vogliono
# tenere.
SHARED_ITEMS = [maintenance.ITEM_SESSION, maintenance.ITEM_HISTORY]


def _print_group(label: str, items: list[Path]) -> None:
    if not items:
        return
    print(f"{label} ({len(items)}):")
    for p in items:
        try:
            shown = p.relative_to(REPO_ROOT)
        except ValueError:
            shown = p
        print(f"  - {shown}")


def _extra_present() -> list[Path]:
    return [p for p in EXTRA_FILES + [cache_path()] if p.exists()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reset stato utente del tool (preferenze, cache, cartella download).",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="non chiedere conferma")
    parser.add_argument("--dry-run", action="store_true", help="mostra cosa farebbe, senza cancellare")
    args = parser.parse_args(argv)

    extra = _extra_present()
    surveys = {key: maintenance.survey(key) for key in SHARED_ITEMS}
    downloads = maintenance.survey(maintenance.ITEM_DOWNLOADS)

    files_present = extra + [p for s in surveys.values() for p in s.paths]
    dirs_with_content = [downloads.root] if downloads.paths else []

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

    for p in extra:
        p.unlink()

    results = maintenance.clear_items(SHARED_ITEMS + [maintenance.ITEM_DOWNLOADS])
    for result in results:
        if not result.ok:
            print(f"[ATTENZIONE] {result.key}: {result.error}")

    print("\nStato utente ripulito.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
