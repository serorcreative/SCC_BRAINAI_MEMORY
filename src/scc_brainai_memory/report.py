"""Rapport de mémoire — synthèse déterministe de l'état de la mémoire BrainAI."""

from __future__ import annotations

from typing import Any, Dict, List


def memory_report(store) -> Dict[str, Any]:
    entries = store.entries
    by_kind = store.counts()
    by_subtype: Dict[str, int] = {}
    for e in entries:
        key = f"{e.kind}:{e.subtype}" if e.subtype else e.kind
        by_subtype[key] = by_subtype.get(key, 0) + 1
    timestamps = [e.timestamp for e in entries]
    redacted = sum(1 for e in entries if e.redacted)
    audit = store.audit()
    return {
        "as_of": store.config.as_of,
        "totals": {
            "entries": len(entries),
            "sessions": len(store.sessions()),
            "redacted_entries": redacted,
        },
        "by_kind": by_kind,
        "by_subtype": dict(sorted(by_subtype.items())),
        "range": {"first": min(timestamps) if timestamps else None,
                  "last": max(timestamps) if timestamps else None},
        "learnings": by_kind.get("learning", 0),
        "preferences": by_kind.get("preference", 0),
        "traces": by_kind.get("trace", 0),
        "integrity_ok": audit["integrity"]["ok"],
        "privacy_ok": audit["privacy"]["ok"],
        "retention": {
            "max_age_days": store.config.max_age_days,
            "max_entries_per_kind": store.config.max_entries_per_kind,
            "protected_kinds": list(store.config.protected_kinds),
        },
    }


def render_markdown(report: Dict[str, Any]) -> str:
    t = report["totals"]
    lines: List[str] = [
        "# Mémoire BrainAI — rapport d'état",
        "",
        f"> Instantané déterministe — `as_of` : {report.get('as_of')}",
        "",
        "## Totaux",
        "",
        f"- **Entrées** : {t['entries']} (dont {t['redacted_entries']} caviardée(s))",
        f"- **Sessions** : {t['sessions']}",
        f"- **Apprentissages** : {report['learnings']} · **Préférences** : {report['preferences']} · **Traces** : {report['traces']}",
        f"- **Période** : {report['range']['first']} → {report['range']['last']}",
        "",
        "## Répartition par genre",
        "",
        "| Genre | Nombre |",
        "|-------|--------|",
    ]
    for k, v in report["by_kind"].items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Intégrité & confidentialité",
        "",
        f"- **Chaîne d'audit intègre** : {report['integrity_ok']}",
        f"- **Aucune donnée sensible résiduelle** : {report['privacy_ok']}",
        "",
        "## Rétention",
        "",
        f"- âge max : {report['retention']['max_age_days']} j · "
        f"max/genre : {report['retention']['max_entries_per_kind']} · "
        f"genres protégés : {report['retention']['protected_kinds']}",
        "",
        "*Rapport généré par la mémoire BrainAI — déterministe, sans réseau ni LLM.*",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["memory_report", "render_markdown"]
