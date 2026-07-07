"""Tests d'écriture contrôlée, confidentialité et modèle."""

from __future__ import annotations

from scc_brainai_memory.privacy import REDACTED, Redactor


def test_write_event_and_search(store):
    e = store.record_event("intent", {"intent": "governance"})
    assert e.kind == "event" and e.subtype == "intent"
    found = store.search(subtype="intent")
    assert len(found) == 1 and found[0]["id"] == e.id


def test_secret_is_redacted(store):
    e = store.record_event("request", {"query": "hello", "password": "hunter2",
                                       "token": "sk-ABCDEF1234567890ABCD"})
    assert e.redacted is True
    assert e.data["password"] == REDACTED
    assert e.data["token"] == REDACTED
    assert e.data["query"] == "hello"


def test_raw_data_never_stored(store):
    e = store.record_event("result", {"raw": "BIGBLOB", "raw_data": {"x": 1}})
    assert e.data["raw"] == REDACTED
    assert e.data["raw_data"] == REDACTED


def test_value_pattern_redaction():
    red = Redactor()
    scrubbed, changed = red.scrub({"note": "eyJhbGci.eyJzdWIi.SflKxwRJ"})
    assert changed is True
    assert scrubbed["note"] == REDACTED


def test_preference_and_learning(store):
    p = store.set_preference("langue", "fr")
    learning = store.add_learning("les demandes governance mobilisent 4 agents",
                                  evidence=[p.id], confidence=0.8)
    assert p.kind == "preference"
    assert learning.kind == "learning"
    assert store.counts()["preference"] == 1
    assert store.counts()["learning"] == 1


def test_long_value_truncated(store):
    e = store.record_event("note", {"blob_text": "x" * 5000})
    assert e.redacted is True
    assert "[TRUNCATED]" in e.data["blob_text"]
