"""Tests intégration Kernel (non invasive), export et déterminisme."""

from __future__ import annotations

import json

from scc_brainai_memory.core.config import MemoryConfig
from scc_brainai_memory.recorder import KernelRecorder, RecordingKernel
from scc_brainai_memory.store import BrainMemoryStore


def test_record_kernel_response(store, kernel_response):
    rec = KernelRecorder(store).record_response(kernel_response)
    # les 7 facettes de l'expérience sont mémorisées + une trace
    assert len(rec["events"]) == 7
    subtypes = {e["subtype"] for e in store.search(kind="event")}
    assert {"request", "intent", "plan", "agents", "decision", "runtime", "result"} <= subtypes
    trace = store.get(rec["trace_id"])
    assert trace["kind"] == "trace"
    assert trace["data"]["intent"] == "inspect"


def test_record_error_response(store, kernel_response):
    kernel_response["ok"] = False
    kernel_response["runtime"]["status"] = "failed"
    kernel_response["runtime"]["error"] = "boom"
    KernelRecorder(store).record_response(kernel_response)
    errors = store.search(subtype="error")
    assert len(errors) == 1
    assert errors[0]["data"]["error"] == "boom"


def test_recording_kernel_wrapper(store, kernel_response):
    class FakeKernel:
        def handle(self, query, **kw):
            return dict(kernel_response, request={"query": query, "actor": "brainai", "autonomy": "A3"})

    wrapped = RecordingKernel(FakeKernel(), store)
    resp = wrapped.handle("état du système")
    assert resp["ok"] is True
    assert store.counts()["trace"] == 1  # le cycle a été mémorisé


def test_export_json_and_markdown(store, kernel_response, tmp_path):
    KernelRecorder(store).record_response(kernel_response)
    data = store.export_json()
    assert data["counts"]["trace"] == 1
    md = store.export_markdown()
    assert "# Mémoire BrainAI" in md
    jp = store.export_json(tmp_path / "m.json")
    assert jp.exists()


def test_export_never_leaks_secret(store):
    store.record_event("request", {"query": "x", "password": "hunter2"})
    blob = json.dumps(store.export_dict(), ensure_ascii=False)
    assert "hunter2" not in blob
    assert "[REDACTED]" in blob


def test_deterministic_recording(config, kernel_response):
    def build(d):
        s = BrainMemoryStore(config=MemoryConfig(data_dir=d))
        KernelRecorder(s).record_response(kernel_response)
        return s.export_dict()
    import tempfile, pathlib
    a = build(pathlib.Path(tempfile.mkdtemp()))
    b = build(pathlib.Path(tempfile.mkdtemp()))
    assert json.dumps(a, sort_keys=True, ensure_ascii=False) == \
           json.dumps(b, sort_keys=True, ensure_ascii=False)


def test_report_shape(store, kernel_response):
    KernelRecorder(store).record_response(kernel_response)
    r = store.report()
    assert r["integrity_ok"] is True
    assert r["privacy_ok"] is True
    assert r["totals"]["entries"] == 8  # 7 events + 1 trace
