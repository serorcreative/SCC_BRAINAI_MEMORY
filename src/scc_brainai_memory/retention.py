"""Politique de rétention — purge contrôlée, déterministe et auditée.

Applique deux règles optionnelles : **âge maximal** et **nombre maximal par
genre**. Certains genres sont **protégés** (apprentissages, préférences) et ne sont
jamais purgés automatiquement. La purge est une opération délibérée et tracée.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from scc_brainai_memory.core.model import MemoryEntry


@dataclass
class RetentionPolicy:
    max_age_days: Optional[int] = None
    max_entries_per_kind: Optional[int] = None
    protected_kinds: List[str] = field(default_factory=lambda: ["learning", "preference"])

    def apply(self, entries: List[MemoryEntry], as_of: str) -> Tuple[List[MemoryEntry], List[MemoryEntry]]:
        """Retourne (conservées, purgées), dans l'ordre chronologique d'origine."""
        keep_flags = {e.id: True for e in entries}

        # Règle 1 — âge maximal.
        if self.max_age_days is not None:
            cutoff = _parse(as_of) - timedelta(days=self.max_age_days)
            for e in entries:
                if e.kind in self.protected_kinds:
                    continue
                ts = _parse(e.timestamp)
                if ts is not None and ts < cutoff:
                    keep_flags[e.id] = False

        # Règle 2 — nombre maximal par genre (garde les plus récentes).
        if self.max_entries_per_kind is not None:
            by_kind: dict = {}
            for e in entries:
                by_kind.setdefault(e.kind, []).append(e)
            for kind, items in by_kind.items():
                if kind in self.protected_kinds:
                    continue
                if len(items) <= self.max_entries_per_kind:
                    continue
                # trie par (timestamp, id) et retire les plus anciennes surnuméraires
                ordered = sorted(items, key=lambda e: (e.timestamp, e.id))
                excess = len(ordered) - self.max_entries_per_kind
                for e in ordered[:excess]:
                    keep_flags[e.id] = False

        kept = [e for e in entries if keep_flags[e.id]]
        purged = [e for e in entries if not keep_flags[e.id]]
        return kept, purged

    def to_dict(self) -> dict:
        return {"max_age_days": self.max_age_days,
                "max_entries_per_kind": self.max_entries_per_kind,
                "protected_kinds": list(self.protected_kinds)}


def _parse(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


__all__ = ["RetentionPolicy"]
