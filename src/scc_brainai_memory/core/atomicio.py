"""Écriture atomique de fichier (L2 store-safety).

Garantie : le fichier cible n'apparaît **jamais** partiellement écrit. Un crash
laisse soit l'ancien contenu complet, soit le nouveau contenu complet.

Procédé (§6 contrat L2) : fichier temporaire dans le **même** répertoire → write
complet → flush → fsync(temp) si supporté → ``os.replace`` (atomique POSIX, même
système de fichiers) → fsync du répertoire parent si supporté → cleanup du temp
en cas d'échec.

Note d'inode : ``os.replace`` remplace l'inode de la cible. Un verrou ``flock``
ne doit donc JAMAIS être posé sur un fichier réécrit par cette fonction — utiliser
un fichier de lock dédié (voir ``locking.py``).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Union


def _fsync_dir(dirpath: Path) -> None:
    """fsync du répertoire pour persister le rename (best-effort, borné aux OS supportés)."""
    flag = getattr(os, "O_DIRECTORY", None)
    if flag is None:
        return
    fd = None
    try:
        fd = os.open(str(dirpath), flag)
        os.fsync(fd)
    except (OSError, AttributeError):
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _atomic_write(path: Path, data: Union[str, bytes], *, binary: bool, encoding: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp_path = tmp
    try:
        if binary:
            with os.fdopen(fd, "wb") as f:
                f.write(data)                       # type: ignore[arg-type]
                f.flush()
                os.fsync(f.fileno())
        else:
            with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
                f.write(data)                       # type: ignore[arg-type]
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp_path, str(path))             # atomique (même répertoire)
        tmp_path = None                              # replace a consommé le temp
        _fsync_dir(path.parent)
        return path
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def atomic_write_text(path: Union[str, Path], data: str, encoding: str = "utf-8") -> Path:
    """Écrit ``data`` (texte) atomiquement dans ``path``."""
    return _atomic_write(Path(path), data, binary=False, encoding=encoding)


def atomic_write_bytes(path: Union[str, Path], data: bytes) -> Path:
    """Écrit ``data`` (octets) atomiquement dans ``path``."""
    return _atomic_write(Path(path), data, binary=True, encoding="utf-8")


__all__ = ["atomic_write_text", "atomic_write_bytes"]
