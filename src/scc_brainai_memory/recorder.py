"""Intégration au Kernel BrainAI — **non invasive**.

Le Kernel expose déjà une sortie publique (le dict renvoyé par ``handle``). La
mémoire s'y branche **sans modifier le Kernel** : ``KernelRecorder`` ingère cette
réponse et en extrait l'expérience (demande, intention, plan, agents, décisions,
exécution Runtime, résultat, erreurs), puis écrit une **trace** reliant le tout.

``RecordingKernel`` enveloppe n'importe quel objet exposant ``handle`` (duck-typé)
pour enregistrer automatiquement — préparation à une future intégration directe.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scc_brainai_memory.core.model import EventType, MemoryTrace
from scc_brainai_memory.store import BrainMemoryStore


class KernelRecorder:
    """Transforme une réponse publique du Kernel en entrées de mémoire."""

    def __init__(self, store: BrainMemoryStore):
        self.store = store

    def record_response(self, response: Dict[str, Any],
                        session_id: Optional[str] = None) -> Dict[str, Any]:
        req = response.get("request", {})
        actor = req.get("actor", "brainai")
        session = session_id or self.store._ensure_default_session(actor).id  # continuité

        event_ids: List[str] = []

        def ev(subtype: str, data: Dict[str, Any], tags=None) -> None:
            entry = self.store.record_event(subtype, data, session_id=session,
                                            actor=actor, tags=tags or [subtype])
            event_ids.append(entry.id)

        # 1–7. Expérience détaillée.
        ev(EventType.REQUEST.value, {"query": req.get("query", ""),
                                     "autonomy": req.get("autonomy", "")})
        ev(EventType.INTENT.value, {"intent": response.get("intent", "")})
        plan = response.get("plan", {})
        ev(EventType.PLAN.value, {"intent": plan.get("intent"),
                                  "steps": len(plan.get("steps", [])),
                                  "actions": sorted({s.get("action") for s in plan.get("steps", [])})})
        agents = [a.get("id") for a in response.get("agents", [])]
        ev(EventType.AGENTS.value, {"agents": agents})
        gov = response.get("governance", {})
        rt = response.get("runtime", {})
        ev(EventType.DECISION.value, {"doctrines": gov.get("doctrines", []),
                                      "adrs": gov.get("adrs", []),
                                      "human_approval_required": rt.get("human_approval_required", False)})
        ev(EventType.RUNTIME.value, {"job_id": rt.get("job_id"), "kind": rt.get("kind"),
                                     "status": rt.get("status"), "trust": rt.get("trust")})

        ok = bool(response.get("ok")) and rt.get("status") in (None, "succeeded")
        if ok:
            ev(EventType.RESULT.value, {"ok": True, "provider": response.get("provider", {}).get("selected")})
        else:
            ev(EventType.ERROR.value, {"ok": response.get("ok"),
                                       "runtime_status": rt.get("status"),
                                       "error": rt.get("error", "")}, tags=["error"])

        # 15. Trace de continuité reliant les événements.
        trace = MemoryTrace(
            request={"query": req.get("query", ""), "autonomy": req.get("autonomy", "")},
            intent=response.get("intent", ""),
            plan={"intent": plan.get("intent"), "steps": len(plan.get("steps", []))},
            agents=agents,
            runtime={"job_id": rt.get("job_id"), "kind": rt.get("kind"), "status": rt.get("status")},
            result={"ok": ok, "provider": response.get("provider", {}).get("selected")},
            event_ids=event_ids, session_id=session, actor=actor,
            tags=["trace", response.get("intent", "")],
        )
        entry = self.store.record_trace(trace)
        return {"trace_id": entry.id, "session": session, "events": event_ids}


class RecordingKernel:
    """Enveloppe un Kernel (duck-typé ``handle``) pour mémoriser chaque cycle."""

    def __init__(self, kernel, store: BrainMemoryStore):
        self._kernel = kernel
        self._recorder = KernelRecorder(store)

    def handle(self, query, **kwargs) -> Dict[str, Any]:
        response = self._kernel.handle(query, **kwargs)
        self._recorder.record_response(response)
        return response


__all__ = ["KernelRecorder", "RecordingKernel"]
