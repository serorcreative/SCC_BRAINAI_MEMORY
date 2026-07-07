"""Configuration de la mémoire BrainAI (JSON, sans dépendance).

La mémoire BrainAI enregistre l'**expérience du Kernel** (demandes, intentions,
plans, agents, décisions, exécutions, résultats, erreurs, préférences,
apprentissages, traces) — distincte de SCC_MEMORY (objets cognitifs).
Persistance locale JSONL, append-only, déterministe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from scc_brainai_memory.core.errors import ConfigError

MEMORY_ROOT = Path(__file__).resolve().parents[3]         # .../11_BRAINAI_MEMORY
DEFAULT_SCC_ROOT = MEMORY_ROOT.parent                      # .../01_CCSC
DEFAULT_CONFIG_PATH = MEMORY_ROOT / "config" / "memory.json"

DEFAULT_AS_OF = "2026-07-06T00:00:00+00:00"


@dataclass
class MemoryConfig:
    """Emplacements et politique de la mémoire."""

    memory_root: Path = MEMORY_ROOT
    scc_root: Path = DEFAULT_SCC_ROOT
    data_dir: Path = MEMORY_ROOT / "data"
    as_of: str = DEFAULT_AS_OF
    # Politique de rétention (voir retention.py).
    max_age_days: Optional[int] = None            # None = illimité
    max_entries_per_kind: Optional[int] = None    # None = illimité
    protected_kinds: List[str] = field(default_factory=lambda: ["learning", "preference"])
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def entries_path(self) -> Path:
        return self.data_dir / "brain_memory.jsonl"

    @property
    def sessions_path(self) -> Path:
        return self.data_dir / "brain_sessions.jsonl"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_root": str(self.memory_root),
            "data_dir": str(self.data_dir),
            "as_of": self.as_of,
            "max_age_days": self.max_age_days,
            "max_entries_per_kind": self.max_entries_per_kind,
            "protected_kinds": list(self.protected_kinds),
        }


def _resolve(base: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def load_config(path: Optional[Path] = None) -> MemoryConfig:
    config = MemoryConfig()
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    if not target.exists():
        if path is not None:
            raise ConfigError(f"Configuration introuvable : {target}")
        return config
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Configuration illisible ({target}) : {exc}") from exc

    base = config.memory_root
    paths = raw.get("paths", {})
    if "data_dir" in paths:
        config.data_dir = _resolve(base, paths["data_dir"])
    config.as_of = str(raw.get("as_of", DEFAULT_AS_OF))
    retention = raw.get("retention", {})
    config.max_age_days = retention.get("max_age_days", config.max_age_days)
    config.max_entries_per_kind = retention.get("max_entries_per_kind", config.max_entries_per_kind)
    config.protected_kinds = list(retention.get("protected_kinds", config.protected_kinds))
    config.extra = dict(raw.get("extra", {}))
    return config


__all__ = ["MEMORY_ROOT", "DEFAULT_SCC_ROOT", "DEFAULT_AS_OF", "MemoryConfig", "load_config"]
