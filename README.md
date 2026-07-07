# SCC BrainAI Memory

**Mémoire officielle de BrainAI — l'expérience propre du Kernel.**

Distincte de **SCC_MEMORY** (qui conserve les *objets cognitifs* de la chaîne SCC),
BrainAI Memory conserve l'**expérience du Kernel** : demandes utilisateur,
intentions détectées, plans produits, agents mobilisés, décisions prises,
exécutions Runtime, résultats, erreurs, préférences non sensibles, apprentissages,
traces et **continuité entre sessions**.

> **Confidentialité garantie** : jamais de secret, token, mot de passe ni donnée RAW
> (caviardage systématique). Mémoire **append-only**, **auditable** (chaîne
> d'empreintes), avec **purge**, **export** et **rapport**. Stdlib pur,
> **déterministe**, sans réseau.

## Non-duplication & intégration non invasive

- **SCC_MEMORY (05)** garde les objets cognitifs — responsabilité différente, **non
  dupliquée**.
- **Kernel BrainAI (10)** n'est **pas modifié** : la mémoire consomme sa **sortie
  publique** (`handle()`), via `KernelRecorder` / `RecordingKernel`.

## Installation

```bash
cd 11_BRAINAI_MEMORY
python -m pip install -e .        # expose la commande `scc-brain-memory`
```

Aucune dépendance externe.

## Utilisation (CLI)

```bash
scc-brain-memory remember "Quelles doctrines gouvernent la gouvernance ?"  # exécute le Kernel et mémorise
scc-brain-memory report        # rapport d'état de la mémoire
scc-brain-memory audit         # intégrité (chaîne) + confidentialité
scc-brain-memory search --subtype decision --text doctrine
scc-brain-memory sessions      # continuité entre sessions
scc-brain-memory export --format md
scc-brain-memory retention     # applique la politique de rétention (purge auditée)
scc-brain-memory self-check
```

## Utilisation (Python)

```python
from scc_brainai_memory import BrainMemoryStore, KernelRecorder

store = BrainMemoryStore()
store.set_preference("langue", "fr")
store.add_learning("les demandes governance mobilisent 4 agents", confidence=0.8)

# intégration au Kernel (sortie publique) — aucune modification du Kernel
KernelRecorder(store).record_response(kernel_response)
print(store.report()["totals"])
```

## Composants

`BrainMemoryStore` · `MemoryEntry` · `MemoryEvent` · `MemorySession` ·
`MemoryPreference` · `MemoryLearning` · `MemoryTrace` · `MemoryIndex` ·
`RetentionPolicy` · `KernelRecorder` / `RecordingKernel`.

Détails : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/MEMORY_MODEL.md`](docs/MEMORY_MODEL.md) ·
[`docs/PRIVACY.md`](docs/PRIVACY.md) ·
[`docs/RETENTION_AUDIT.md`](docs/RETENTION_AUDIT.md) ·
[`docs/KERNEL_INTEGRATION.md`](docs/KERNEL_INTEGRATION.md).

## Tests

```bash
python -m pytest -q      # 23 tests (déterministes, isolés)
```
