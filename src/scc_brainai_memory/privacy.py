"""Garde-fous de confidentialité — jamais de secret ni de donnée RAW.

Toute écriture passe par le **redacteur** : les clés sensibles (mot de passe,
token, clé d'API…) et les valeurs ressemblant à des secrets sont remplacées par
``[REDACTED]`` ; les champs de **donnée RAW** sont refusés/retirés. Déterministe.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

REDACTED = "[REDACTED]"

# Clés dont la valeur est toujours masquée (comparaison insensible à la casse).
SENSITIVE_KEYS = {
    "password", "passwd", "pwd", "secret", "token", "access_token", "refresh_token",
    "api_key", "apikey", "authorization", "auth", "bearer", "private_key",
    "client_secret", "session_token", "credentials", "credential", "signature",
    "cookie", "set-cookie", "ssn", "card", "cvv",
}

# Clés dont le contenu est de la donnée RAW (interdite en mémoire BrainAI).
RAW_KEYS = {"raw", "raw_data", "raw_content", "content_raw", "blob", "binary"}

# Motifs de valeurs ressemblant à des secrets.
_VALUE_PATTERNS = [
    re.compile(r"^sk-[A-Za-z0-9]{16,}$"),                 # clés type OpenAI
    re.compile(r"^gh[pousr]_[A-Za-z0-9]{20,}$"),          # tokens GitHub
    re.compile(r"^Bearer\s+[A-Za-z0-9._\-]+$", re.I),     # en-tête Bearer
    re.compile(r"^eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$"),  # JWT
    re.compile(r"^[A-Fa-f0-9]{40,}$"),                    # longues empreintes hex
    re.compile(r"^AKIA[0-9A-Z]{12,}$"),                   # clés AWS
]

# Taille maximale d'une chaîne mémorisée (au-delà : tronquée — anti-RAW/anti-dump).
MAX_STR = 2000


class Redactor:
    """Nettoie récursivement une structure avant mémorisation (déterministe)."""

    def __init__(self, max_str: int = MAX_STR):
        self._max_str = max_str

    def scrub(self, value: Any) -> Tuple[Any, bool]:
        """Retourne (valeur nettoyée, a_été_modifiée)."""
        return self._scrub(value, key="")

    def _scrub(self, value: Any, key: str) -> Tuple[Any, bool]:
        k = key.lower()
        if k in RAW_KEYS or k in SENSITIVE_KEYS:
            # Déjà caviardé => sûr (aucun changement) ; l'audit ne le signale pas.
            if value == REDACTED:
                return REDACTED, False
            return REDACTED, True
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            changed = False
            for kk in sorted(value.keys(), key=str):
                nv, c = self._scrub(value[kk], key=str(kk))
                out[kk] = nv
                changed = changed or c
            return out, changed
        if isinstance(value, (list, tuple)):
            items = []
            changed = False
            for item in value:
                nv, c = self._scrub(item, key=key)
                items.append(nv)
                changed = changed or c
            return items, changed
        if isinstance(value, str):
            return self._scrub_str(value)
        return value, False

    def _scrub_str(self, text: str) -> Tuple[str, bool]:
        if text == REDACTED:
            return text, False
        stripped = text.strip()
        for pat in _VALUE_PATTERNS:
            if pat.match(stripped):
                return REDACTED, True
        if len(text) > self._max_str:
            return text[: self._max_str] + "…[TRUNCATED]", True
        return text, False

    def scan(self, value: Any) -> bool:
        """Vrai s'il reste une donnée sensible détectable (contrôle d'audit)."""
        _, changed = self.scrub(value)
        return changed


__all__ = ["Redactor", "REDACTED", "SENSITIVE_KEYS", "RAW_KEYS"]
