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


class MemoryCorruption(MemoryError):
    """Corruption fail-closed du journal (ligne interne invalide ou rupture de chaîne).

    L2 §8 : une ligne invalide/rompue **au milieu** du journal, ou toute rupture de
    chaîne d'empreinte, est traitée comme une corruption explicite (jamais un skip
    silencieux). Seule une dernière ligne tronquée à EOF autorise une récupération
    bornée et observable.
    """


class NotFoundError(MemoryError):
    """Entrée ou session introuvable."""


__all__ = ["MemoryError", "ConfigError", "WriteRejected", "IntegrityError",
           "MemoryCorruption", "NotFoundError"]
