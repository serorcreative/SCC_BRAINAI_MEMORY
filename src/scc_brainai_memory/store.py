"""BrainMemoryStore — mémoire officielle de BrainAI (façade).

Enregistre l'**expérience du Kernel** de façon **contrôlée** (garde-fous de
confidentialité), **append-only** et **auditable** (chaîne d'empreintes).

Sécurité L2 (store-safety / concurrence) :
- Toute mutation s'exécute sous **verrou 2-niveaux** (``locking.StoreLock`` : intra
  puis inter-process via flock sur lockfile dédié). Sous verrou : **reload disque
  (+ réparation éventuelle) → validation → mutation → persistance**. Aucun calcul
  critique ne dépend d'un snapshot antérieur au verrou.
- ``record_event`` — ordre de commit : préparer l'état → **atomic_write sessions**
  → **append journal EN DERNIER** (le journal est le commit logique).
- ``brain_memory.jsonl`` = source de vérité (entries + rattachement ``session_id``).
  ``brain_sessions.jsonl`` = snapshot **hybride** : ``entry_ids`` réconcilié depuis
  le journal (dérivable) ; ``updated_at``/``status``/``summary``/``meta``/
  ``started_at``/``actor`` **autoritaires** dans le snapshot (non dérivables, jamais
  reconstruits/inventés).
- Corruption journal : ligne interne invalide ou rupture de chaîne ⇒ FAIL-CLOSED ;
  seule une dernière ligne tronquée **sans ``\\n`` final** ⇒ récupération bornée +
  ``truncated_tail`` (observable), réparée sous lock avant tout nouvel append.

Limites connues (L2) :
- Pas de transaction ACID multi-fichiers. Cohérence par : journal = commit logique ;
  snapshot atomique ; ``entry_ids`` réconciliable ; métadonnées lifecycle autoritaires.
- Les appends ne font volontairement PAS de fsync par événement (§7). Une toute
  dernière entrée non durable perdue/tronquée après crash peut théoriquement voir son
  ID réémis après réparation si cet ID n'existe dans aucun préfixe valide survivant :
  l'unicité **historique absolue** d'un ID **non durable** n'est pas garantie — cela
  découle directement de la politique de durabilité L2 ratifiée.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from scc_brainai_memory.audit import audit_report
from scc_brainai_memory.core.atomicio import atomic_write_text
from scc_brainai_memory.core.clock import Clock, FixedClock
from scc_brainai_memory.core.config import MemoryConfig, load_config
from scc_brainai_memory.core.errors import MemoryCorruption
from scc_brainai_memory.core.locking import StoreLock
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
        # Observables L2 (état de la dernière lecture disque).
        self.truncated_tail: bool = False
        self.reconciliation_required: bool = False
        self.lock_timeout: float = float(self.config.extra.get("lock_timeout", 10.0))
        if autoload:
            self.load()

    # ================================================================== #
    # Verrou & reload gouverné
    # ================================================================== #
    def _lock(self) -> StoreLock:
        return StoreLock(self.config.lock_path, timeout=self.lock_timeout)

    def _repair_truncation_locked(self) -> None:
        """Réparation gouvernée (jamais en load()). Réécrit atomiquement le préfixe
        valide déjà vérifié/chaîné, supprimant la queue tronquée, pour qu'un append
        ultérieur ne produise pas ``queue_invalide + nouvelle_ligne``."""
        if self.truncated_tail:
            self._persist_entries_atomic()   # = exactement self._entries (préfixe valide)
            # truncated_tail reste True : observabilité de la récupération pour cette opération.

    def _reload_locked(self) -> None:
        self._load_from_disk()               # lecture seule (peut poser truncated_tail=True)
        self._repair_truncation_locked()     # réparation atomique si tail tronquée

    # ================================================================== #
    # Écriture contrôlée
    # ================================================================== #
    def write(self, memorable) -> MemoryEntry:
        with self._lock():
            self._reload_locked()
            return self._write_locked(memorable)

    def _write_locked(self, memorable) -> MemoryEntry:
        actor = getattr(memorable, "actor", "brainai") or "brainai"
        session_id = getattr(memorable, "session_id", "") or ""
        if not session_id:
            session_id = self._ensure_default_session_locked(actor).id

        payload, p_changed = self.redactor.scrub(memorable.payload())
        tags, t_changed = self.redactor.scrub(list(getattr(memorable, "tags", []) or []))

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

        session = self._sessions.get(session_id)
        if session is not None:
            session.entry_ids.append(entry.id)      # dérivable
            session.updated_at = entry.timestamp     # activité courante (autoritaire à l'écriture)
        # Ordre de commit : snapshot sessions (atomique) PUIS append journal EN DERNIER.
        self._persist_sessions_atomic()
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
        with self._lock():
            self._reload_locked()
            now = self.clock.now()
            session = MemorySession(id=self._next_session_id(), actor=actor,
                                    status=SessionStatus.OPEN.value, started_at=now,
                                    updated_at=now, meta=dict(meta or {}))
            self._sessions[session.id] = session
            self._persist_sessions_atomic()
            return session

    def get_session(self, session_id: str) -> Optional[MemorySession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str, summary: str = "") -> MemorySession:
        with self._lock():
            self._reload_locked()
            session = self._sessions[session_id]
            session.status = SessionStatus.CLOSED.value   # autoritaire (non dérivable)
            session.summary = summary                      # autoritaire
            session.updated_at = self.clock.now()          # lifecycle (non dérivable)
            self._persist_sessions_atomic()
            return session

    def sessions(self) -> List[MemorySession]:
        return [self._sessions[k] for k in sorted(self._sessions)]

    def resume(self, actor: str = "brainai") -> Optional[MemorySession]:
        owned = [s for s in self._sessions.values() if s.actor == actor]
        if not owned:
            return None
        opens = [s for s in owned if s.status == SessionStatus.OPEN.value]
        return sorted(opens or owned, key=lambda s: (s.started_at, s.id))[-1]

    def _ensure_default_session(self, actor: str = "brainai") -> MemorySession:
        """Compat gouvernée : garantit (et persiste) une session par défaut pour l'acteur.

        Contrat externe conservé (utilisé par ``KernelRecorder``) : sous verrou,
        reload → ensure → persistance atomique du snapshot.
        """
        with self._lock():
            self._reload_locked()
            session = self._ensure_default_session_locked(actor)
            self._persist_sessions_atomic()
            return session

    def _ensure_default_session_locked(self, actor: str) -> MemorySession:
        existing = self.resume(actor)
        if existing is not None and existing.status == SessionStatus.OPEN.value:
            return existing
        now = self.clock.now()
        session = MemorySession(id=self._next_session_id(), actor=actor,
                                status=SessionStatus.OPEN.value, started_at=now,
                                updated_at=now, meta={})
        self._sessions[session.id] = session
        return session  # persistance assurée par le write appelant

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
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return path

    def export_markdown(self, path: Optional[Path] = None) -> Any:
        md = render_markdown(memory_report(self))
        if path is None:
            return md
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, md)
        return path

    # ================================================================== #
    # Audit & rétention
    # ================================================================== #
    def audit(self) -> Dict[str, Any]:
        return audit_report(self._entries, self.redactor)

    def apply_retention(self, policy: Optional[RetentionPolicy] = None) -> Dict[str, Any]:
        with self._lock():
            self._reload_locked()
            policy = policy or RetentionPolicy(
                max_age_days=self.config.max_age_days,
                max_entries_per_kind=self.config.max_entries_per_kind,
                protected_kinds=list(self.config.protected_kinds))
            pre_seq = self._entry_seq                       # max de séquence PRÉ-rétention (inclut purgés)
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
            # Événement retention : ID > max historique pré-rétention (aucune réutilisation d'identité).
            sid = self._ensure_default_session_locked("memory").id
            rid = self._next_entry_id()                     # _entry_seq==pre_seq -> rid = pre_seq+1
            assert int(rid.rsplit("_", 1)[-1], 16) > pre_seq
            payload, changed = self.redactor.scrub({"purged": report["purged"], "policy": policy.to_dict()})
            rentry = MemoryEntry(id=rid, kind=EntryKind.EVENT.value, subtype="retention",
                                 session_id=sid, actor="memory", timestamp=self.clock.now(),
                                 tags=["retention", "audit"], data=payload, redacted=bool(changed))
            rentry.finalize(prev)                           # chaîné APRÈS kept
            final_entries = kept + [rentry]
            self._entries = final_entries
            self._by_id = {e.id: e for e in final_entries}
            self.index.rebuild(final_entries)
            self._last_hash = rentry.hash
            self._reconcile_membership()                    # entry_ids seulement
            session = self._sessions.get(sid)
            if session is not None:
                session.updated_at = rentry.timestamp        # même sémantique que _write_locked (autoritaire)
            # COMMIT : snapshot atomique, puis JOURNAL FINAL atomique (kept + retention) en un seul write.
            self._persist_sessions_atomic()
            self._persist_entries_atomic()
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
        atomic_write_text(json_path, json.dumps(self.report(), ensure_ascii=False, indent=2) + "\n")
        atomic_write_text(md_path, render_markdown(self.report()))
        return {"json": str(json_path), "markdown": str(md_path)}

    @property
    def entries(self) -> List[MemoryEntry]:
        return list(self._entries)

    def counts(self) -> Dict[str, int]:
        return self.index.counts()

    # ================================================================== #
    # Persistance
    # ================================================================== #
    def _append_entry_line(self, entry: MemoryEntry) -> None:
        # Append sous lock + flush explicite ; PAS de fsync par événement (L2 §7).
        self.config.ensure_directories()
        with self.config.entries_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            f.flush()

    def _persist_entries_atomic(self) -> None:
        atomic_write_text(self.config.entries_path,
                          "".join(json.dumps(e.to_dict(), ensure_ascii=False) + "\n" for e in self._entries))

    def _persist_sessions_atomic(self) -> None:
        atomic_write_text(self.config.sessions_path,
                          "".join(json.dumps(self._sessions[s].to_dict(), ensure_ascii=False) + "\n"
                                  for s in sorted(self._sessions)))

    # -- réconciliation (membership dérivable UNIQUEMENT) --------------- #
    @staticmethod
    def _membership_from(entries: List[MemoryEntry]) -> Dict[str, List[str]]:
        m: Dict[str, List[str]] = {}
        for e in entries:
            m.setdefault(e.session_id, []).append(e.id)
        return m

    def _reconcile_membership(self) -> None:
        m = self._membership_from(self._entries)
        for sid, s in self._sessions.items():
            s.entry_ids = list(m.get(sid, []))    # updated_at PRÉSERVÉ (autoritaire)

    # -- chargement (lecture seule) + réconciliation -------------------- #
    def load(self) -> None:
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        self._entries = []
        self._by_id = {}
        self._sessions = {}
        self._last_hash = ""
        self._entry_seq = 0
        self._session_seq = 0
        self.index = MemoryIndex()
        self.truncated_tail = False
        self.reconciliation_required = False

        ep = self.config.entries_path
        if ep.exists():
            raw = ep.read_text(encoding="utf-8")
            ends_nl = raw.endswith("\n")
            lines = raw.splitlines()
            n = len(lines)
            prev_hash = ""
            for i, line in enumerate(lines):
                s = line.strip()
                if not s:
                    raise MemoryCorruption(f"ligne vide (L{i+1}) dans brain_memory.jsonl")
                try:
                    obj = json.loads(s)
                except json.JSONDecodeError:
                    if i == n - 1 and not ends_nl:
                        self.truncated_tail = True   # tail tronquée (pas de \n final) : récupération bornée
                        break
                    raise MemoryCorruption(
                        f"JSON invalide (L{i+1}) dans brain_memory.jsonl "
                        + ("[dernière ligne complète => corruption]" if (i == n - 1 and ends_nl) else "[au milieu]"))
                e = MemoryEntry.from_dict(obj)
                if e.prev_hash != prev_hash or not e.verify():
                    raise MemoryCorruption(f"rupture de chaîne d'empreinte (L{i+1})")  # FAIL même en dernière ligne
                self._entries.append(e)
                self._by_id[e.id] = e
                prev_hash = e.hash
            self.index.rebuild(self._entries)
            if self._entries:
                self._last_hash = self._entries[-1].hash
                self._entry_seq = _max_seq(e.id for e in self._entries)

        snap: Dict[str, MemorySession] = {}
        sp = self.config.sessions_path
        if sp.exists():
            for line in sp.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except json.JSONDecodeError as exc:
                    raise MemoryCorruption(f"brain_sessions.jsonl invalide : {exc}") from exc
                ms = MemorySession.from_dict(obj)
                snap[ms.id] = ms

        membership = self._membership_from(self._entries)
        recon = False
        for sid, ms in snap.items():
            ids = membership.get(sid, [])
            if list(ms.entry_ids) != ids:
                recon = True
            ms.entry_ids = list(ids)                # canonique depuis le journal ; updated_at PRÉSERVÉ
            self._sessions[sid] = ms
        # Journal référençant une session absente du snapshot => FAIL-CLOSED (aucune invention lifecycle).
        for sid in membership:
            if sid and sid not in self._sessions:
                raise MemoryCorruption(
                    f"session '{sid}' référencée par le journal mais absente du snapshot "
                    f"(fail-closed : métadonnées lifecycle non dérivables, aucune reconstruction)")
        if self._sessions:
            self._session_seq = _max_seq(self._sessions.keys())
        self.reconciliation_required = recon

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
