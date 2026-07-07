"""Tests sessions/continuité, audit d'intégrité et rétention."""

from __future__ import annotations

from scc_brainai_memory.core.config import MemoryConfig
from scc_brainai_memory.retention import RetentionPolicy
from scc_brainai_memory.store import BrainMemoryStore


def test_session_continuity(store):
    s1 = store.open_session(actor="frederique")
    store.record_event("intent", {"intent": "graph"}, session_id=s1.id, actor="frederique")
    resumed = store.resume("frederique")
    assert resumed.id == s1.id
    assert s1.id in {s.id for s in store.sessions()}
    assert store.get_session(s1.id).entry_ids  # l'entrée est rattachée


def test_close_session(store):
    s = store.open_session(actor="a")
    store.close_session(s.id, summary="terminé")
    assert store.get_session(s.id).status == "closed"
    assert store.get_session(s.id).summary == "terminé"


def test_integrity_chain_ok(store):
    for i in range(5):
        store.record_event("intent", {"intent": f"i{i}"})
    audit = store.audit()
    assert audit["ok"] is True
    assert audit["integrity"]["ok"] is True
    assert audit["integrity"]["first_broken"] is None


def test_integrity_detects_tampering(store):
    store.record_event("intent", {"intent": "a"})
    store.record_event("intent", {"intent": "b"})
    # falsification directe d'une entrée en mémoire
    store._entries[0].data["intent"] = "TAMPERED"
    audit = store.audit()
    assert audit["integrity"]["ok"] is False


def test_persistence_roundtrip(config):
    s1 = BrainMemoryStore(config=config)
    s1.record_event("intent", {"intent": "persist"})
    s1.add_learning("apprentissage persistant")
    # relire depuis le disque
    s2 = BrainMemoryStore(config=config)
    assert s2.counts()["event"] == 1
    assert s2.counts()["learning"] == 1
    assert s2.audit()["ok"] is True


def test_retention_purges_and_protects(config):
    store = BrainMemoryStore(config=config)
    for i in range(6):
        store.record_event("intent", {"n": i})
    store.add_learning("protégé")            # genre protégé
    store.set_preference("k", "v")           # genre protégé
    policy = RetentionPolicy(max_entries_per_kind=2, protected_kinds=["learning", "preference"])
    report = store.apply_retention(policy)
    assert report["purged"] == 4             # 6 events -> garde 2
    # les apprentissages/préférences sont protégés
    assert store.counts()["learning"] == 1
    assert store.counts()["preference"] == 1
    # la chaîne reste intègre après compaction
    assert store.audit()["integrity"]["ok"] is True
