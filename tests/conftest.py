"""Fixtures des tests de la mémoire BrainAI (isolées en tmp, déterministes)."""

from __future__ import annotations

import pytest

from scc_brainai_memory.core.config import MemoryConfig
from scc_brainai_memory.store import BrainMemoryStore


@pytest.fixture
def config(tmp_path):
    return MemoryConfig(data_dir=tmp_path / "data")


@pytest.fixture
def store(config):
    return BrainMemoryStore(config=config)


@pytest.fixture
def kernel_response(config):
    """Réponse type du Kernel BrainAI (sortie publique) pour tester l'intégration."""
    return {
        "ok": True,
        "as_of": config.as_of,
        "request": {"query": "état du système", "actor": "brainai", "autonomy": "A3"},
        "intent": "inspect",
        "plan": {"intent": "inspect", "steps": [
            {"action": "inspect_health"}, {"action": "observe_supervision"}]},
        "agents": [{"id": "SCC-AGENT-0015"}, {"id": "SCC-AGENT-0020"}],
        "governance": {"doctrines": ["SCC-DOC-0013"], "adrs": ["ADR-0003"]},
        "runtime": {"job_id": "job_x", "kind": "echo", "status": "succeeded",
                    "trust": "T1", "human_approval_required": False},
        "provider": {"selected": "deterministic"},
    }
