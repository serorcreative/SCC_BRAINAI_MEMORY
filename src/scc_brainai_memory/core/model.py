"""Modèle de la mémoire BrainAI.

Une **MemoryEntry** est l'unité persistée canonique (enveloppe append-only,
chaînée par empreinte pour l'audit). Les types métier — **MemoryEvent**,
**MemoryPreference**, **MemoryLearning**, **MemoryTrace** — sont des *mémorables*
typés qui se convertissent en entrée. **MemorySession** assure la continuité.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from scc_brainai_memory.core.clock import digest


class EntryKind(str, Enum):
    EVENT = "event"
    TRACE = "trace"
    PREFERENCE = "preference"
    LEARNING = "learning"


class EventType(str, Enum):
    """Sous-types d'événements de l'expérience BrainAI."""

    REQUEST = "request"            # demande utilisateur reçue
    INTENT = "intent"             # intention détectée
    PLAN = "plan"                 # plan produit
    AGENTS = "agents"             # agents mobilisés
    DECISION = "decision"         # décision prise
    RUNTIME = "runtime"           # exécution Runtime
    RESULT = "result"             # résultat consolidé
    ERROR = "error"               # erreur rencontrée


class SessionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


# --------------------------------------------------------------------------- #
# Entrée persistée (enveloppe)
# --------------------------------------------------------------------------- #
@dataclass
class MemoryEntry:
    """Unité de mémoire persistée, chaînée par empreinte (tamper-evident)."""

    id: str
    kind: str
    subtype: str
    session_id: str
    actor: str
    timestamp: str
    tags: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    redacted: bool = False
    prev_hash: str = ""
    hash: str = ""

    def _payload_for_hash(self) -> Dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "subtype": self.subtype,
            "session_id": self.session_id, "actor": self.actor,
            "timestamp": self.timestamp, "tags": list(self.tags),
            "data": self.data, "redacted": self.redacted, "prev_hash": self.prev_hash,
        }

    def finalize(self, prev_hash: str) -> "MemoryEntry":
        """Chaîne l'entrée sur la précédente et calcule son empreinte."""
        self.prev_hash = prev_hash
        self.hash = digest(self._payload_for_hash())
        return self

    def verify(self) -> bool:
        return self.hash == digest(self._payload_for_hash())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "subtype": self.subtype,
            "session_id": self.session_id, "actor": self.actor,
            "timestamp": self.timestamp, "tags": list(self.tags), "data": dict(self.data),
            "redacted": self.redacted, "prev_hash": self.prev_hash, "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryEntry":
        return cls(
            id=str(d.get("id", "")), kind=str(d.get("kind", "")),
            subtype=str(d.get("subtype", "")), session_id=str(d.get("session_id", "")),
            actor=str(d.get("actor", "")), timestamp=str(d.get("timestamp", "")),
            tags=list(d.get("tags", []) or []), data=dict(d.get("data", {}) or {}),
            redacted=bool(d.get("redacted", False)),
            prev_hash=str(d.get("prev_hash", "")), hash=str(d.get("hash", "")),
        )


# --------------------------------------------------------------------------- #
# Mémorables typés (se convertissent en enveloppe)
# --------------------------------------------------------------------------- #
@dataclass
class MemoryEvent:
    """Un fait de l'expérience BrainAI (demande, intention, plan, décision…)."""

    subtype: str
    data: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    actor: str = "brainai"
    tags: List[str] = field(default_factory=list)
    kind: str = EntryKind.EVENT.value

    def payload(self) -> Dict[str, Any]:
        return dict(self.data)


@dataclass
class MemoryPreference:
    """Préférence utilisateur **non sensible**."""

    key: str
    value: Any
    scope: str = "user"
    session_id: str = ""
    actor: str = "brainai"
    kind: str = EntryKind.PREFERENCE.value
    subtype: str = "set"

    def payload(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value, "scope": self.scope}

    @property
    def tags(self) -> List[str]:
        return ["preference", self.scope]


@dataclass
class MemoryLearning:
    """Apprentissage exploitable dérivé de l'expérience."""

    statement: str
    evidence: List[str] = field(default_factory=list)   # ids d'entrées justificatives
    confidence: float = 0.5
    session_id: str = ""
    actor: str = "brainai"
    tags: List[str] = field(default_factory=list)
    kind: str = EntryKind.LEARNING.value
    subtype: str = "insight"

    def payload(self) -> Dict[str, Any]:
        return {"statement": self.statement, "evidence": list(self.evidence),
                "confidence": self.confidence}


@dataclass
class MemoryTrace:
    """Trace ordonnée d'un cycle complet du Kernel (continuité et lignage)."""

    request: Dict[str, Any]
    intent: str = ""
    plan: Dict[str, Any] = field(default_factory=dict)
    agents: List[str] = field(default_factory=list)
    runtime: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    event_ids: List[str] = field(default_factory=list)
    session_id: str = ""
    actor: str = "brainai"
    tags: List[str] = field(default_factory=list)
    kind: str = EntryKind.TRACE.value
    subtype: str = "kernel_cycle"

    def payload(self) -> Dict[str, Any]:
        return {"request": self.request, "intent": self.intent, "plan": self.plan,
                "agents": list(self.agents), "runtime": self.runtime,
                "result": self.result, "event_ids": list(self.event_ids)}


# --------------------------------------------------------------------------- #
# Session (continuité)
# --------------------------------------------------------------------------- #
@dataclass
class MemorySession:
    """Fil de continuité regroupant les entrées d'un même contexte d'usage."""

    id: str
    actor: str = "brainai"
    status: str = SessionStatus.OPEN.value
    started_at: str = ""
    updated_at: str = ""
    entry_ids: List[str] = field(default_factory=list)
    summary: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "actor": self.actor, "status": self.status,
            "started_at": self.started_at, "updated_at": self.updated_at,
            "entry_ids": list(self.entry_ids), "summary": self.summary, "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemorySession":
        return cls(
            id=str(d.get("id", "")), actor=str(d.get("actor", "brainai")),
            status=str(d.get("status", "open")), started_at=str(d.get("started_at", "")),
            updated_at=str(d.get("updated_at", "")), entry_ids=list(d.get("entry_ids", []) or []),
            summary=str(d.get("summary", "")), meta=dict(d.get("meta", {}) or {}),
        )


__all__ = [
    "EntryKind", "EventType", "SessionStatus",
    "MemoryEntry", "MemoryEvent", "MemoryPreference", "MemoryLearning",
    "MemoryTrace", "MemorySession",
]
