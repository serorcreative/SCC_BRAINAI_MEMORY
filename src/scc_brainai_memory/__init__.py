"""SCC BrainAI Memory — mémoire officielle de l'expérience du Kernel BrainAI.

Distincte de SCC_MEMORY (objets cognitifs), cette mémoire conserve l'**expérience
propre du Kernel** : demandes, intentions, plans, agents mobilisés, décisions,
exécutions Runtime, résultats, erreurs, préférences non sensibles, apprentissages,
traces et continuité entre sessions.

Garde-fous : jamais de secret, token, mot de passe ni donnée RAW (caviardage
systématique). Mémoire append-only, auditable (chaîne d'empreintes), avec purge,
export et rapport. Déterministe, stdlib pur, sans réseau. Intégration au Kernel
**non invasive** (consomme sa sortie publique).
"""

from __future__ import annotations

__version__ = "1.0.0"

from scc_brainai_memory.core.config import MemoryConfig, load_config
from scc_brainai_memory.core.model import (
    MemoryEntry,
    MemoryEvent,
    MemoryLearning,
    MemoryPreference,
    MemorySession,
    MemoryTrace,
)
from scc_brainai_memory.recorder import KernelRecorder, RecordingKernel
from scc_brainai_memory.retention import RetentionPolicy
from scc_brainai_memory.store import BrainMemoryStore

__all__ = [
    "__version__",
    "BrainMemoryStore",
    "MemoryConfig",
    "load_config",
    "MemoryEntry",
    "MemoryEvent",
    "MemorySession",
    "MemoryPreference",
    "MemoryLearning",
    "MemoryTrace",
    "RetentionPolicy",
    "KernelRecorder",
    "RecordingKernel",
]
