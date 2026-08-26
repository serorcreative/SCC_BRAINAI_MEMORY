"""Verrou 2-niveaux fail-closed pour stores fichier (L2 store-safety, §5).

Deux niveaux, sans dépendance externe :

1. **Intra-process** : sérialisation ré-entrante partagée **par chemin canonique de
   lockfile**. Deux instances de store visant le même ``data_dir`` partagent le même
   verrou process-local (une simple ``threading.Lock`` par instance ne suffit pas).
2. **Inter-process** : ``fcntl.flock`` **exclusif** sur un **fichier de lock dédié**
   (jamais la cible réécrite par ``os.replace``, dont l'inode change).

Réentrance : dans un même thread, l'acquisition imbriquée réutilise le même
descripteur (compteur de profondeur) — ``flock`` n'est pris qu'une fois, ce qui
évite l'auto-blocage (un second ``open`` créerait une autre *open file description*
et ``flock`` s'auto-bloquerait).

Fail-closed :
- ``timeout`` borné (jamais d'attente infinie) → ``LockTimeout``.
- ``fcntl`` indisponible (plateforme) → ``LockUnavailable`` (aucune dégradation
  silencieuse : on refuse d'écrire sans garantie inter-process).
"""

from __future__ import annotations

import errno
import os
import threading
import time
from pathlib import Path
from typing import Dict

try:
    import fcntl  # POSIX uniquement
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - plateforme sans fcntl
    fcntl = None  # type: ignore
    _HAVE_FCNTL = False


class LockError(RuntimeError):
    """Erreur de verrouillage (base)."""


class LockUnavailable(LockError):
    """Verrouillage inter-process impossible (fcntl absent) — fail-closed."""


class LockTimeout(LockError):
    """Verrou non acquis dans le délai imparti — fail-closed."""


class _Entry:
    __slots__ = ("rlock", "fd", "depth")

    def __init__(self) -> None:
        self.rlock = threading.RLock()
        self.fd = None
        self.depth = 0


_REGISTRY: Dict[str, _Entry] = {}
_REGISTRY_GUARD = threading.Lock()


def _entry_for(canonical: str) -> _Entry:
    with _REGISTRY_GUARD:
        e = _REGISTRY.get(canonical)
        if e is None:
            e = _Entry()
            _REGISTRY[canonical] = e
        return e


def _canonical(lock_path: Path) -> str:
    # Chemin canonique stable indépendant de l'existence préalable du fichier.
    parent = lock_path.parent
    base = parent.resolve() if parent.exists() else parent
    return str(base / lock_path.name)


class StoreLock:
    """Context manager : verrou intra-process (ré-entrant) puis flock inter-process.

    Ordre : process-local lock → flock dédié → (section critique) → unlock flock →
    unlock process-local.
    """

    def __init__(self, lock_path, timeout: float = 10.0, poll: float = 0.05) -> None:
        self.lock_path = Path(lock_path)
        self.canonical = _canonical(self.lock_path)
        self.timeout = float(timeout)
        self.poll = float(poll)
        self._entry = _entry_for(self.canonical)

    def __enter__(self) -> "StoreLock":
        if not _HAVE_FCNTL:
            raise LockUnavailable(
                "fcntl.flock indisponible : verrou inter-process impossible (fail-closed, aucune dégradation)"
            )
        e = self._entry
        if not e.rlock.acquire(timeout=self.timeout):
            raise LockTimeout(f"process-local lock timeout ({self.timeout}s): {self.canonical}")
        try:
            if e.depth == 0:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o600)
                deadline = time.monotonic() + self.timeout
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as ex:
                        if ex.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                            os.close(fd)
                            raise
                        if time.monotonic() >= deadline:
                            os.close(fd)
                            raise LockTimeout(f"flock timeout ({self.timeout}s): {self.lock_path}")
                        time.sleep(self.poll)
                e.fd = fd
            e.depth += 1
        except BaseException:
            e.rlock.release()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        e = self._entry
        try:
            e.depth -= 1
            if e.depth == 0 and e.fd is not None:
                try:
                    fcntl.flock(e.fd, fcntl.LOCK_UN)
                finally:
                    os.close(e.fd)
                    e.fd = None
        finally:
            e.rlock.release()
        return False


__all__ = ["StoreLock", "LockError", "LockUnavailable", "LockTimeout"]
