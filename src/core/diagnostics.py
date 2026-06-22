# Diagnostica passiva: heartbeat periodico, memoria processo, marcatori di
# sessione. Funzioni pure (nessuna dipendenza da PyQt6/rete): testabili in
# isolamento. Niente di qui modifica il comportamento di download.
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading

log = logging.getLogger("diagnostics")


def get_process_memory_mb() -> float | None:
    """Working set RSS del processo corrente in MB. None se non disponibile.

    Usa psutil SOLO se gia' presente (non e' una dipendenza di questo
    progetto); altrimenti fallback stdlib via ctypes/psapi su Windows.
    Nessuna eccezione esce da qui: in caso di problemi ritorna None e il
    chiamante logga "n/d" invece di far fallire l'heartbeat.
    """
    try:
        import psutil  # noqa: PLC0415 - opzionale, solo se gia' installato
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except ImportError:
        pass
    except Exception:
        log.debug("psutil presente ma memory_info() fallita", exc_info=True)

    if sys.platform == "win32":
        try:
            import ctypes.wintypes as wintypes

            class _ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            # GetCurrentProcess() ritorna uno pseudo-handle a 64 bit (-1 sign
            # extended sull'intero registro). Senza restype/argtypes espliciti,
            # ctypes lo tratta come c_int a 32 bit: il valore troncato passato
            # a GetProcessMemoryInfo e' un HANDLE non valido (ERROR_INVALID_HANDLE,
            # codice 6) e la funzione fallisce silenziosamente (ok=0), motivo
            # per cui finora questa funzione tornava sempre None su Windows.
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.GetCurrentProcess.argtypes = []
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(_ProcessMemoryCounters),
                wintypes.DWORD,
            ]

            counters = _ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
            handle = kernel32.GetCurrentProcess()
            ok = psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            )
            if ok:
                return counters.WorkingSetSize / (1024 * 1024)
        except Exception:
            log.debug("ctypes/psapi memoria fallito", exc_info=True)
    return None


def format_heartbeat(
    mem_rss_mb: float | None, threads: int, download_attivi: int, pool_vivi: int,
) -> str:
    mem_str = f"{mem_rss_mb:.1f}" if mem_rss_mb is not None else "n/d"
    return (
        f"HEARTBEAT mem_rss={mem_str} threads={threads} "
        f"download_attivi={download_attivi} pool_vivi={pool_vivi}"
    )


def log_heartbeat(download_attivi: int, pool_vivi: int) -> None:
    mem = get_process_memory_mb()
    threads = threading.active_count()
    log.info(format_heartbeat(mem, threads, download_attivi, pool_vivi))


def log_session_start(app_version: str) -> None:
    log.info("SESSION START v%s pid=%d", app_version, os.getpid())


def log_session_clean_exit() -> None:
    log.info("SESSION CLEAN EXIT")
