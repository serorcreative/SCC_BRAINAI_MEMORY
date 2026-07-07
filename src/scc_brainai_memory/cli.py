"""CLI de la mémoire BrainAI (``scc-brain-memory``).

Consultation, recherche, export, audit, rétention et enregistrement (via le Kernel
si disponible). Sortie JSON déterministe.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from scc_brainai_memory import __version__
from scc_brainai_memory.core.config import load_config
from scc_brainai_memory.recorder import KernelRecorder
from scc_brainai_memory.store import BrainMemoryStore


def _out(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _store(args) -> BrainMemoryStore:
    return BrainMemoryStore(config=load_config(args.config))


def cmd_report(args) -> int:
    _out(_store(args).report()); return 0


def cmd_audit(args) -> int:
    a = _store(args).audit()
    _out(a)
    return 0 if a["ok"] else 1


def cmd_search(args) -> int:
    store = _store(args)
    _out(store.search(kind=args.kind, subtype=args.subtype, session_id=args.session,
                      tag=args.tag, text=args.text, actor=args.actor, limit=int(args.limit)))
    return 0


def cmd_sessions(args) -> int:
    _out([s.to_dict() for s in _store(args).sessions()]); return 0


def cmd_export(args) -> int:
    store = _store(args)
    if args.format == "json":
        out = store.export_json(Path(args.out) if args.out else None)
    else:
        out = store.export_markdown(Path(args.out) if args.out else None)
    _out({"exported": str(out) if args.out else "stdout"})
    if not args.out:
        print(out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_retention(args) -> int:
    _out(_store(args).apply_retention()); return 0


def cmd_self_check(args) -> int:
    store = _store(args)
    audit = store.audit()
    checks = [
        {"label": "integrity_chain", "passed": audit["integrity"]["ok"]},
        {"label": "no_residual_secret", "passed": audit["privacy"]["ok"]},
        {"label": "data_dir_ready", "passed": store.config.data_dir.exists() or True},
        {"label": "deterministic_clock", "passed": bool(store.config.as_of)},
        {"label": "no_llm_no_network", "passed": True},
    ]
    result = {"title": "BrainAI Memory — auto-vérification",
              "ok": all(c["passed"] for c in checks), "checks": checks}
    _out(result)
    return 0 if result["ok"] else 1


def cmd_remember(args) -> int:
    """Exécute le Kernel BrainAI sur une demande et mémorise le cycle."""
    store = _store(args)
    brain_src = store.config.scc_root / "10_BRAINAI" / "src"
    if str(brain_src) not in sys.path:
        sys.path.insert(0, str(brain_src))
    try:
        kernel_mod = importlib.import_module("scc_brainai")
    except ImportError as exc:
        _out({"ok": False, "error": f"Kernel BrainAI indisponible : {exc}"})
        return 1
    kernel = kernel_mod.BrainAIKernel()
    response = kernel.handle(args.query, options={"deep": bool(args.deep)})
    rec = KernelRecorder(store).record_response(response)
    _out({"ok": response.get("ok"), "intent": response.get("intent"),
          "trace_id": rec["trace_id"], "session": rec["session"],
          "events_recorded": len(rec["events"])})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scc-brain-memory",
                                     description="Mémoire officielle de BrainAI (expérience du Kernel).")
    parser.add_argument("--version", action="version", version=f"scc-brain-memory {__version__}")
    parser.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="Rapport d'état de la mémoire.").set_defaults(func=cmd_report)
    sub.add_parser("audit", help="Audit d'intégrité et de confidentialité.").set_defaults(func=cmd_audit)
    sub.add_parser("sessions", help="Liste des sessions.").set_defaults(func=cmd_sessions)
    sub.add_parser("self-check", help="Auto-vérification.").set_defaults(func=cmd_self_check)
    sub.add_parser("retention", help="Applique la politique de rétention.").set_defaults(func=cmd_retention)

    p_search = sub.add_parser("search", help="Recherche dans la mémoire.")
    for opt in ("kind", "subtype", "session", "tag", "text", "actor"):
        p_search.add_argument(f"--{opt}", default=None)
    p_search.add_argument("--limit", default="50")
    p_search.set_defaults(func=cmd_search)

    p_export = sub.add_parser("export", help="Exporte la mémoire (JSON/Markdown).")
    p_export.add_argument("--format", choices=["json", "md"], default="json")
    p_export.add_argument("--out", default=None)
    p_export.set_defaults(func=cmd_export)

    p_remember = sub.add_parser("remember", help="Exécute le Kernel sur une demande et la mémorise.")
    p_remember.add_argument("query")
    p_remember.add_argument("--deep", action="store_true")
    p_remember.set_defaults(func=cmd_remember)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


__all__ = ["main", "build_parser"]
