"""Noyau de la mémoire BrainAI : config, erreurs, horloge, modèle."""

from __future__ import annotations

from scc_brainai_memory.core.clock import (
    Clock,
    FixedClock,
    IdFactory,
    SequentialFactory,
    SystemClock,
    UuidFactory,
    canonical,
    digest,
)
from scc_brainai_memory.core.config import MemoryConfig, load_config
from scc_brainai_memory.core.errors import (
    ConfigError,
    IntegrityError,
    MemoryError,
    NotFoundError,
    WriteRejected,
)
from scc_brainai_memory.core.model import (
    EntryKind,
    EventType,
    MemoryEntry,
    MemoryEvent,
    MemoryLearning,
    MemoryPreference,
    MemorySession,
    MemoryTrace,
    SessionStatus,
)

__all__ = [
    "Clock", "SystemClock", "FixedClock", "IdFactory", "UuidFactory",
    "SequentialFactory", "canonical", "digest",
    "MemoryConfig", "load_config",
    "MemoryError", "ConfigError", "WriteRejected", "IntegrityError", "NotFoundError",
    "EntryKind", "EventType", "SessionStatus",
    "MemoryEntry", "MemoryEvent", "MemoryPreference", "MemoryLearning",
    "MemoryTrace", "MemorySession",
]
