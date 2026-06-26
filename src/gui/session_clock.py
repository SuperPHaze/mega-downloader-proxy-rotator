"""Clock di sessione con auto-freeze a fine sessione.

Pura logica testabile: il tempo "ora" e' sempre un parametro, niente time.time()
implicito. Usato dal widget Statistiche per mostrare un tempo attivo che si congela
quando tutti i job terminano e si riarma se ne parte uno nuovo."""
from __future__ import annotations


class SessionClock:
    def __init__(self) -> None:
        self._started_at: float | None = None
        self._frozen_at: float | None = None

    def start(self, now: float) -> None:
        """Avvia (o riavvia) la sessione. Resetta freeze."""
        self._started_at = now
        self._frozen_at = None

    def update(self, now: float, all_terminated: bool) -> None:
        """Da chiamare al tick periodico.

        Se tutti i job sono terminati e il clock non e' gia' congelato, lo congela
        a `now`. Se NON sono tutti terminati ma il clock era congelato, lo
        scongela (un nuovo job e' partito): il tempo precedente NON viene perso,
        il clock riprende a contare dall'origine.
        """
        if self._started_at is None:
            return
        if all_terminated and self._frozen_at is None:
            self._frozen_at = now
        elif not all_terminated and self._frozen_at is not None:
            self._frozen_at = None

    def elapsed(self, now: float) -> float:
        """Secondi attivi: dal start al freeze (se congelato) o a now."""
        if self._started_at is None:
            return 0.0
        end = self._frozen_at if self._frozen_at is not None else now
        return max(0.0, end - self._started_at)

    def is_frozen(self) -> bool:
        return self._frozen_at is not None

    def is_started(self) -> bool:
        return self._started_at is not None

    def reset(self) -> None:
        self._started_at = None
        self._frozen_at = None
