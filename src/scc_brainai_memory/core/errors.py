"""Hiérarchie d'exceptions de la mémoire BrainAI."""

from __future__ import annotations


class MemoryError(Exception):
    """Erreur de base de la mémoire BrainAI."""


class ConfigError(MemoryError):
    """Configuration absente, illisible ou invalide."""


class WriteRejected(MemoryError):
    """Écriture refusée par un garde-fou (donnée RAW, taille, contenu interdit)."""


class IntegrityError(MemoryError):
    """Rupture d'intégrité détectée dans la chaîne d'audit."""


class NotFoundError(MemoryError):
    """Entrée ou session introuvable."""


__all__ = ["MemoryError", "ConfigError", "WriteRejected", "IntegrityError", "NotFoundError"]
