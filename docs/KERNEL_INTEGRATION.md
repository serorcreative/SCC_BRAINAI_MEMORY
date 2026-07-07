# Intégration au Kernel BrainAI — non invasive

> **Le Kernel n'est pas modifié.** La mémoire se branche sur sa **sortie publique**
> (le dict renvoyé par `handle()`), déjà disponible. C'est le point d'extension
> exigé : « sauf si un point d'extension public existe déjà » — il existe.

## 1. Principe

Le Kernel `BrainAIKernel.handle(query)` renvoie une réponse structurée contenant
déjà toute l'expérience à mémoriser : `request`, `intent`, `plan`, `agents`,
`governance`, `runtime`, `provider`, `ok`. La mémoire **consomme** cette réponse ;
elle n'a besoin d'aucun crochet interne au Kernel.

## 2. Deux modes d'intégration

### a) `KernelRecorder` — après coup

```python
from scc_brainai import BrainAIKernel
from scc_brainai_memory import BrainMemoryStore, KernelRecorder

kernel, store = BrainAIKernel(), BrainMemoryStore()
response = kernel.handle("Quelles doctrines gouvernent la gouvernance ?")
KernelRecorder(store).record_response(response)   # 7 événements + 1 trace
```

### b) `RecordingKernel` — enveloppe transparente

```python
from scc_brainai_memory import RecordingKernel

brain = RecordingKernel(BrainAIKernel(), BrainMemoryStore())
brain.handle("état de santé du système")   # exécute ET mémorise, même signature
```

`RecordingKernel` accepte **tout objet exposant `handle`** (duck-typé) : aucune
dépendance dure au Kernel, aucune modification.

## 3. Ce qui est extrait de la réponse

| Événement mémorisé | Source dans la réponse |
|--------------------|------------------------|
| `request` | `response["request"]` (query, autonomie) |
| `intent` | `response["intent"]` |
| `plan` | `response["plan"]` (intention, nb d'étapes, actions) |
| `agents` | `response["agents"]` (ids) |
| `decision` | `response["governance"]` + `runtime.human_approval_required` |
| `runtime` | `response["runtime"]` (job, kind, statut) |
| `result` / `error` | `response["ok"]` + `runtime.status` |
| `trace` | relie tous les `event_ids` du cycle |

## 4. Continuité entre sessions

À l'ingestion, la mémoire rattache le cycle à la **session courante** de l'acteur
(`resume(actor)`), ou en ouvre une. Plusieurs demandes successives d'un même acteur
s'enchaînent dans **la même session** — base de la continuité et de la relecture.

## 5. Confidentialité à la frontière

La réponse du Kernel passe par le **caviardage** avant mémorisation : si une demande
utilisateur contenait un secret, il serait `[REDACTED]` en mémoire. La frontière
Kernel → Mémoire est donc sûre par construction.

## 6. Préparation à une intégration future

Le jour où l'on voudra une intégration plus étroite (ex. le Kernel appelant
lui-même la mémoire), il suffira d'injecter un `RecordingKernel` ou un
`KernelRecorder` **là où le Kernel est instancié** — sans toucher au cœur du Kernel.
La CLI `scc-brain-memory remember "<query>"` en fait déjà la démonstration.
