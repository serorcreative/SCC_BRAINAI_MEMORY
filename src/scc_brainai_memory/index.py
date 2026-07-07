"""MemoryIndex — index de recherche en mémoire (déterministe).

Indexe les entrées par genre, sous-type, session, étiquette et texte (recherche
plein-texte simple sur la charge sérialisée). Aucune base externe.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scc_brainai_memory.core.clock import canonical
from scc_brainai_memory.core.model import MemoryEntry


class MemoryIndex:
    def __init__(self) -> None:
        self._by_id: Dict[str, MemoryEntry] = {}
        self._text: Dict[str, str] = {}   # id -> texte indexable minuscule

    def add(self, entry: MemoryEntry) -> None:
        self._by_id[entry.id] = entry
        blob = f"{entry.kind} {entry.subtype} {' '.join(entry.tags)} {canonical(entry.data)}"
        self._text[entry.id] = blob.lower()

    def rebuild(self, entries: List[MemoryEntry]) -> None:
        self._by_id.clear()
        self._text.clear()
        for e in entries:
            self.add(e)

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return self._by_id.get(entry_id)

    def search(self, *, kind: Optional[str] = None, subtype: Optional[str] = None,
               session_id: Optional[str] = None, tag: Optional[str] = None,
               text: Optional[str] = None, actor: Optional[str] = None,
               limit: int = 50) -> List[MemoryEntry]:
        q = (text or "").strip().lower()
        results: List[MemoryEntry] = []
        # Itération triée par id → déterminisme (les ids sont séquentiels/horodatés).
        for eid in sorted(self._by_id):
            e = self._by_id[eid]
            if kind and e.kind != kind:
                continue
            if subtype and e.subtype != subtype:
                continue
            if session_id and e.session_id != session_id:
                continue
            if actor and e.actor != actor:
                continue
            if tag and tag not in e.tags:
                continue
            if q and q not in self._text.get(eid, ""):
                continue
            results.append(e)
        if limit and limit > 0:
            results = results[:limit]
        return results

    def counts(self) -> Dict[str, int]:
        by_kind: Dict[str, int] = {}
        for e in self._by_id.values():
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        return dict(sorted(by_kind.items()))

    def __len__(self) -> int:
        return len(self._by_id)


__all__ = ["MemoryIndex"]
