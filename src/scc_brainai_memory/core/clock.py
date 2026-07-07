"""Horloge et fabrique d'identifiants injectables — déterminisme.

Réimplémenté ici en stdlib pur pour garder la mémoire **autonome** (aucun couplage
à un autre module pour une primitive triviale), selon le même patron que les autres
composants SCC. ``FixedClock`` + ``SequentialFactory`` rendent la mémoire rejouable.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


class Clock:
    def now(self) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class SystemClock(Clock):
    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class FixedClock(Clock):
    """Horloge de test/déterminisme : horodatage fixe, +``step`` s par appel."""

    def __init__(self, value: str = "2026-07-06T00:00:00+00:00", step: int = 1):
        self._base = datetime.fromisoformat(value)
        self._step = step
        self._count = 0

    def now(self) -> str:
        stamp = self._base + timedelta(seconds=self._step * self._count)
        self._count += 1
        return stamp.isoformat()


class IdFactory:
    def new(self, prefix: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class UuidFactory(IdFactory):
    def new(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SequentialFactory(IdFactory):
    """Fabrique déterministe : compteur par préfixe."""

    def __init__(self):
        self._counters = {}

    def new(self, prefix: str) -> str:
        counter = self._counters.setdefault(prefix, itertools.count(1))
        return f"{prefix}_{next(counter):012x}"


def canonical(obj: Any) -> str:
    """Sérialisation canonique et stable (pour empreintes reproductibles)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(obj: Any) -> str:
    """Empreinte SHA-256 d'une structure (audit d'intégrité)."""
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


__all__ = ["Clock", "SystemClock", "FixedClock", "IdFactory", "UuidFactory",
           "SequentialFactory", "canonical", "digest"]
