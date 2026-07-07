"""Audit et intégrité de la mémoire BrainAI.

Deux contrôles :

* **chaîne d'empreintes** : chaque entrée est chaînée à la précédente
  (``prev_hash``) et signée (``hash``) ; toute altération est détectable ;
* **confidentialité résiduelle** : aucune donnée sensible ne doit subsister
  (contrôle par le redacteur).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scc_brainai_memory.core.model import MemoryEntry
from scc_brainai_memory.privacy import Redactor


def verify_chain(entries: List[MemoryEntry]) -> Dict[str, Any]:
    """Vérifie l'intégrité de la chaîne append-only."""
    prev = ""
    first_broken: Optional[str] = None
    for e in entries:
        if e.prev_hash != prev or not e.verify():
            first_broken = e.id
            break
        prev = e.hash
    return {"ok": first_broken is None, "count": len(entries), "first_broken": first_broken}


def privacy_audit(entries: List[MemoryEntry], redactor: Optional[Redactor] = None) -> Dict[str, Any]:
    """Vérifie qu'aucune donnée sensible ne subsiste dans les charges."""
    redactor = redactor or Redactor()
    offending: List[str] = []
    for e in entries:
        if redactor.scan(e.data):
            offending.append(e.id)
    return {"ok": not offending, "offending": sorted(offending)}


def audit_report(entries: List[MemoryEntry], redactor: Optional[Redactor] = None) -> Dict[str, Any]:
    chain = verify_chain(entries)
    privacy = privacy_audit(entries, redactor)
    return {
        "ok": chain["ok"] and privacy["ok"],
        "integrity": chain,
        "privacy": privacy,
        "entries": len(entries),
    }


__all__ = ["verify_chain", "privacy_audit", "audit_report"]
