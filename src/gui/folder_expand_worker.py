# Espansione dei link cartella Mega in job-file, fuori dal thread della GUI.
# Una chiamata di rete per cartella (elenco nodi): senza QThread bloccherebbe
# la finestra per tutta la durata della richiesta.
from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import MEGA_FOLDER_MAX_FILES
from src.core.mega_links import is_folder_link
from src.downloader.mega_api import MegaApiError
from src.downloader.mega_folder import deduplicate_job_urls, expand_folder_link
from src.gui.i18n import t, tn

log = logging.getLogger(__name__)


class FolderExpandWorker(QThread):
    """Sostituisce ogni link cartella con i job-file che contiene.

    I link che non sono cartelle passano invariati e nell'ordine originale:
    un incolla misto (cartelle + file singoli) funziona senza casi speciali.
    """

    # (link_espansi, righe_di_report, n_file_oltre_il_limite)
    finished_ok = pyqtSignal(list, list, int)
    failed = pyqtSignal(str)
    # (cartelle_completate, cartelle_totali)
    progress = pyqtSignal(int, int)

    def __init__(self, links: list[str], max_files: int = MEGA_FOLDER_MAX_FILES) -> None:
        super().__init__()
        self._links = list(links)
        self._max_files = max_files
        self._cancelled = False

    def request_cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def _should_abort(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        folders = [u for u in self._links if is_folder_link(u)]
        total = len(folders)
        done = 0
        out: list[str] = []
        report: list[str] = []
        errors = 0
        truncated_total = 0

        for url in self._links:
            if self._cancelled:
                self.failed.emit(t("folder_expand.cancelled"))
                return
            if not is_folder_link(url):
                out.append(url)
                continue
            try:
                expansion = expand_folder_link(
                    url,
                    should_abort=self._should_abort,
                    max_files=self._max_files,
                )
            except MegaApiError as exc:
                errors += 1
                log.warning("[espansione] cartella non espansa (%s): %s", url, exc)
                report.append(t("folder_expand.error_line", url=url, error=exc))
                continue
            except Exception as exc:  # rete/parse imprevisti: non uccidere il thread
                errors += 1
                log.exception("[espansione] errore inatteso su %s", url)
                report.append(
                    t("folder_expand.unexpected_line", url=url, error=exc)
                )
                continue

            jobs = expansion.job_urls()
            if not jobs:
                report.append(
                    t("folder_expand.empty_line", folder=expansion.folder_name)
                )
            else:
                out.extend(jobs)
                # La riga di esito si compone per clausole: ognuna e'
                # autonoma (separatore incluso) e quindi traducibile da
                # sola, altrimenti servirebbe una chiave per ciascuna
                # delle otto combinazioni possibili.
                line = tn(
                    "folder_expand.ok_line",
                    len(jobs),
                    folder=expansion.folder_name,
                )
                if expansion.n_folders:
                    line += tn(
                        "folder_expand.subfolders_suffix", expansion.n_folders
                    )
                if expansion.truncated:
                    truncated_total += expansion.truncated
                    line += t(
                        "folder_expand.truncated_suffix",
                        n=expansion.truncated,
                        max=self._max_files,
                    )
                if expansion.n_skipped:
                    line += t(
                        "folder_expand.skipped_suffix", n=expansion.n_skipped
                    )
                report.append(line)
            done += 1
            self.progress.emit(done, total)

        if not out:
            nothing = t("folder_expand.nothing")
            if errors or report:
                self.failed.emit("\n".join(report) or nothing)
            else:
                self.failed.emit(nothing)
            return
        # Due job non possono condividere la destinazione su disco: qui si vede
        # l'insieme COMPLETO (piu' cartelle insieme), quindi e' l'unico punto in
        # cui la de-collisione puo' essere fatta davvero.
        out, removed = deduplicate_job_urls(out)
        if removed:
            log.warning("[espansione] %d file duplicati rimossi", removed)
            report.append(
                tn("folder_expand.duplicates_removed", removed)
            )
        self.finished_ok.emit(out, report, truncated_total)
