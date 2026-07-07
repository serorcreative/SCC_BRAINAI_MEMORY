"""BrainMemoryStore — mémoire officielle de BrainAI (façade).

Enregistre l'**expérience du Kernel** de façon **contrôlée** (garde-fous de
confidentialité), **append-only** et **auditable** (chaîne d'empreintes). Fournit
écriture, sessions (continuité), recherche, export, audit, rétention et rapport.

Déterministe : horloge injectable (``FixedClock`` par défaut), identifiants
séquentiels, sérialisation canonique.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scc_brainai_memory.audit import audit_report
from scc_brainai_memory.core.clock import Clock, FixedClock
from scc_brainai_memory.core.config import MemoryConfig, load_config
from scc_brainai_memory.core.model import (
    EntryKind,
    MemoryEntry,
    MemoryEvent,
    MemoryLearning,
    MemoryPreference,
    MemorySession,
    MemoryTrace,
    SessionStatus,
)
from scc_brainai_memory.index import MemoryIndex
from scc_brainai_memory.privacy import Redactor
from scc_brainai_memory.report import memory_report, render_markdown
from scc_brainai_memory.retention import RetentionPolicy


class BrainMemoryStore:
    def __init__(self, config: Optional[MemoryConfig] = None, *,
                 clock: Optional[Clock] = None, redactor: Optional[Redactor] = None,
                 autoload: bool = True):
        self.config = config or load_config()
        self.clock = clock or FixedClock(self.config.as_of)
        self.redactor = redactor or Redactor()
        self._entries: List[MemoryEntry] = []
        self._by_id: Dict[str, MemoryEntry] = {}
        self._sessions: Dict[str, MemorySession] = {}
        self._last_hash = ""
        self._entry_seq = 0
        self._session_seq = 0
        self.index = MemoryIndex()
        if autoload:
            self.load()

    # ================================================================== #
    # Écriture contrôlée
    # ================================================================== #
    def write(self, memorable) -> MemoryEntry:
        """Écrit un mémorable typé (Event/Preference/Learning/Trace) sous garde-fous."""
        actor = getattr(memorable, "actor", "brainai") or "brainai"
        session_id = getattr(memorable, "session_id", "") or self._ensure_default_session(actor).id

        payload, p_changed = self.redactor.scrub(memorable.payload())
        tags_in = list(getattr(memorable, "tags", []) or [])
        tags, t_changed = self.redactor.scrub(tags_in)

        entry = MemoryEntry(
            id=self._next_entry_id(),
            kind=getattr(memorable, "kind", EntryKind.EVENT.value),
            subtype=getattr(memorable, "subtype", ""),
            session_id=session_id,
            actor=actor,
            timestamp=self.clock.now(),
            tags=tags,
            data=payload,
            redacted=bool(p_changed or t_changed),
        )
        entry.finalize(self._last_hash)
        self._last_hash = entry.hash
        self._entries.append(entry)
        self._by_id[entry.id] = entry
        self.index.add(entry)
        self._attach_to_session(session_id, entry)
        self._append_entry_line(entry)
        return entry

    def record_event(self, subtype: str, data: Dict[str, Any], session_id: str = "",
                     actor: str = "brainai", tags: Optional[List[str]] = None) -> MemoryEntry:
        return self.write(MemoryEvent(subtype=subtype, data=dict(data), session_id=session_id,
                                      actor=actor, tags=list(tags or [subtype])))

    def set_preference(self, key: str, value: Any, scope: str = "user",
                       session_id: str = "", actor: str = "brainai") -> MemoryEntry:
        return self.write(MemoryPreference(key=key, value=value, scope=scope,
                                           session_id=session_id, actor=actor))

    def add_learning(self, statement: str, evidence: Optional[List[str]] = None,
                     confidence: float = 0.5, tags: Optional[List[str]] = None,
                     session_id: str = "", actor: str = "brainai") -> MemoryEntry:
        return self.write(MemoryLearning(statement=statement, evidence=list(evidence or []),
                                         confidence=confidence, tags=list(tags or ["learning"]),
                                         session_id=session_id, actor=actor))

    def record_trace(self, trace: MemoryTrace) -> MemoryEntry:
        return self.write(trace)

    # ================================================================== #
    # Sessions & continuité
    # ================================================================== #
    def open_session(self, actor: str = "brainai", meta: Optional[Dict[str, Any]] = None) -> MemorySession:
        now = self.clock.now()
        session = MemorySession(id=self._next_session_id(), actor=actor,
                                status=SessionStatus.OPEN.value, started_at=now,
                                updated_at=now, meta=dict(meta or {}))
        self._sessions[session.id] = session
        self._rewrite_sessions()
        return session

    def get_session(self, session_id: str) -> Optional[MemorySession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str, summary: str = "") -> MemorySession:
        session = self._sessions[session_id]
        session.status = SessionStatus.CLOSED.value
        session.summary = summary
        session.updated_at = self.clock.now()
        self._rewrite_sessions()
        return session

    def sessions(self) -> List[MemorySession]:
        return [self._sessions[k] for k in sorted(self._sessions)]

    def resume(self, actor: str = "brainai") -> Optional[MemorySession]:
        """Continuité : dernière session (ouverte de préférence) d'un acteur."""
        owned = [s for s in self._sessions.values() if s.actor == actor]
        if not owned:
            return None
        opens = [s for s in owned if s.status == SessionStatus.OPEN.value]
        pool = opens or owned
        return sorted(pool, key=lambda s: (s.started_at, s.id))[-1]

    def _ensure_default_session(self, actor: str) -> MemorySession:
        existing = self.resume(actor)
        if existing is not None and existing.status == SessionStatus.OPEN.value:
            return existing
        return self.open_session(actor)

    def _attach_to_session(self, session_id: str, entry: MemoryEntry) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.entry_ids.append(entry.id)
        session.updated_at = entry.timestamp
        self._rewrite_sessions()

    # ================================================================== #
    # Recherche
    # ================================================================== #
    def search(self, **kwargs) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.index.search(**kwargs)]

    def get(self, entry_id: str) -> Optional[Dict[str, Any]]:
        e = self._by_id.get(entry_id)
        return e.to_dict() if e else None

    # ================================================================== #
    # Export
    # ================================================================== #
    def export_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.config.as_of,
            "counts": self.index.counts(),
            "sessions": [s.to_dict() for s in self.sessions()],
            "entries": [e.to_dict() for e in self._entries],
            "audit": self.audit(),
        }

    def export_json(self, path: Optional[Path] = None) -> Any:
        data = self.export_dict()
        if path is None:
            return data
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def export_markdown(self, path: Optional[Path] = None) -> Any:
        md = render_markdown(memory_report(self))
        if path is None:
            return md
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        return path

    # ================================================================== #
    # Audit & rétention
    # ================================================================== #
    def audit(self) -> Dict[str, Any]:
        return audit_report(self._entries, self.redactor)

    def apply_retention(self, policy: Optional[RetentionPolicy] = None) -> Dict[str, Any]:
        policy = policy or RetentionPolicy(
            max_age_days=self.config.max_age_days,
            max_entries_per_kind=self.config.max_entries_per_kind,
            protected_kinds=list(self.config.protected_kinds))
        kept, purged = policy.apply(self._entries, self.config.as_of)
        report = {"purged": len(purged), "kept": len(kept),
                  "ids_purged": sorted(e.id for e in purged), "policy": policy.to_dict()}
        if not purged:
            return report

        # Compaction : re-chaînage déterministe des entrées conservées.
        prev = ""
        for e in kept:
            e.finalize(prev)
            prev = e.hash
        self._entries = kept
        self._last_hash = prev
        self._by_id = {e.id: e for e in kept}
        self.index.rebuild(kept)
        self._rewrite_entries()
        # Trace d'audit de la purge (chaînée par-dessus).
        self.record_event("retention", {"purged": report["purged"], "policy": policy.to_dict()},
                          actor="memory", tags=["retention", "audit"])
        return report

    # ================================================================== #
    # Rapport
    # ================================================================== #
    def report(self) -> Dict[str, Any]:
        return memory_report(self)

    def write_report(self, tag: str = "memory") -> Dict[str, str]:
        self.config.ensure_directories()
        json_path = self.config.data_dir / f"{tag}_report.json"
        md_path = self.config.data_dir / f"{tag}_report.md"
        json_path.write_text(json.dumps(self.report(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_markdown(self.report()), encoding="utf-8")
        return {"json": str(json_path), "markdown": str(md_path)}

    # -- accès internes (rapport/tests) --------------------------------- #
    @property
    def entries(self) -> List[MemoryEntry]:
        return list(self._entries)

    def counts(self) -> Dict[str, int]:
        return self.index.counts()

    # ================================================================== #
    # Persistance
    # ================================================================== #
    def _append_entry_line(self, entry: MemoryEntry) -> None:
        self.config.ensure_directories()
        with self.config.entries_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_entries(self) -> None:
        self.config.ensure_directories()
        with self.config.entries_path.open("w", encoding="utf-8") as f:
            for e in self._entries:
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_sessions(self) -> None:
        self.config.ensure_directories()
        with self.config.sessions_path.open("w", encoding="utf-8") as f:
            for sid in sorted(self._sessions):
                f.write(json.dumps(self._sessions[sid].to_dict(), ensure_ascii=False) + "\n")

    def load(self) -> None:
        ep = self.config.entries_path
        if ep.exists():
            for line in ep.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = MemoryEntry.from_dict(json.loads(line))
                    self._entries.append(e)
                    self._by_id[e.id] = e
            self.index.rebuild(self._entries)
            if self._entries:
                self._last_hash = self._entries[-1].hash
                self._entry_seq = _max_seq(e.id for e in self._entries)
        sp = self.config.sessions_path
        if sp.exists():
            for line in sp.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    s = MemorySession.from_dict(json.loads(line))
                    self._sessions[s.id] = s
            if self._sessions:
                self._session_seq = _max_seq(self._sessions.keys())

    # -- identifiants déterministes ------------------------------------- #
    def _next_entry_id(self) -> str:
        self._entry_seq += 1
        return f"mem_{self._entry_seq:012x}"

    def _next_session_id(self) -> str:
        self._session_seq += 1
        return f"ses_{self._session_seq:012x}"


def _max_seq(ids) -> int:
    best = 0
    for i in ids:
        try:
            best = max(best, int(i.rsplit("_", 1)[-1], 16))
        except (ValueError, IndexError):
            continue
    return best


__all__ = ["BrainMemoryStore"]
