"""Tests de la CLI de la mémoire BrainAI."""

from __future__ import annotations

import json

import pytest

from scc_brainai_memory.cli import main
from scc_brainai_memory.recorder import KernelRecorder
from scc_brainai_memory.store import BrainMemoryStore


@pytest.fixture
def populated(config, kernel_response):
    KernelRecorder(BrainMemoryStore(config=config)).record_response(kernel_response)
    return config


def _run(argv, config, capsys):
    rc = main(["--config", str(_write_config(config))] + argv)
    return rc, capsys.readouterr().out


def _write_config(config):
    # écrit un fichier de config pointant vers le data_dir du test
    path = config.data_dir.parent / "memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"paths": {"data_dir": str(config.data_dir)},
                                "as_of": config.as_of}), encoding="utf-8")
    return path


def test_cli_report(populated, capsys):
    rc, out = _run(["report"], populated, capsys)
    data = json.loads(out)
    assert rc == 0
    assert data["totals"]["entries"] == 8


def test_cli_audit(populated, capsys):
    rc, out = _run(["audit"], populated, capsys)
    data = json.loads(out)
    assert rc == 0
    assert data["ok"] is True


def test_cli_search(populated, capsys):
    rc, out = _run(["search", "--subtype", "intent"], populated, capsys)
    data = json.loads(out)
    assert rc == 0
    assert len(data) == 1


def test_cli_self_check(populated, capsys):
    rc, out = _run(["self-check"], populated, capsys)
    data = json.loads(out)
    assert rc == 0
    assert data["ok"] is True
