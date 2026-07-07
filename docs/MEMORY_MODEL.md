# Modèle de la mémoire BrainAI

## 1. L'entrée persistée (`MemoryEntry`)

Unité canonique, **append-only**, chaînée par empreinte :

```json
{
  "id": "mem_000000000001",
  "kind": "event",
  "subtype": "intent",
  "session_id": "ses_000000000001",
  "actor": "brainai",
  "timestamp": "2026-07-06T00:00:00+00:00",
  "tags": ["intent"],
  "data": { "intent": "governance" },
  "redacted": false,
  "prev_hash": "…",
  "hash": "sha256(entrée + prev_hash)"
}
```

`prev_hash`/`hash` forment une **chaîne tamper-evident** : toute altération casse la
vérification (voir [`RETENTION_AUDIT.md`](RETENTION_AUDIT.md)).

## 2. Les mémorables typés

| Type | `kind` | Contenu |
|------|--------|---------|
| **MemoryEvent** | `event` | un fait : `request`, `intent`, `plan`, `agents`, `decision`, `runtime`, `result`, `error` |
| **MemoryPreference** | `preference` | préférence non sensible : `key`, `value`, `scope` |
| **MemoryLearning** | `learning` | apprentissage : `statement`, `evidence`, `confidence` |
| **MemoryTrace** | `trace` | cycle complet du Kernel reliant les événements (lignage) |

Chacun se convertit en `MemoryEntry` via l'enveloppe du store (id, horodatage,
empreinte, caviardage).

## 3. Les huit sous-types d'événement (l'expérience)

| `subtype` | Ce qui est mémorisé |
|-----------|---------------------|
| `request` | la demande utilisateur (query, autonomie) |
| `intent` | l'intention détectée |
| `plan` | le plan (intention, nb d'étapes, actions) |
| `agents` | les agents mobilisés (ids) |
| `decision` | doctrines/ADR retenus, validation humaine T3 requise |
| `runtime` | l'exécution Runtime (job, kind, statut, confiance) |
| `result` | le résultat consolidé (ok, fournisseur) |
| `error` | l'erreur rencontrée (si échec) |

## 4. La session (`MemorySession`) — continuité

Regroupe les entrées d'un même contexte d'usage : `id`, `actor`, `status`
(open/closed), horodatages, `entry_ids`, `summary`. `resume(actor)` retrouve la
dernière session (ouverte de préférence) → **continuité entre sessions**.

## 5. L'index (`MemoryIndex`)

Recherche déterministe par `kind`, `subtype`, `session_id`, `tag`, `actor` et
**texte** (plein-texte sur la charge sérialisée). Itération triée par `id`.

## 6. La trace (`MemoryTrace`) — lignage d'un cycle

Relie, pour une demande, l'intention → le plan → les agents → l'exécution Runtime →
le résultat, avec la liste des `event_ids`. C'est l'unité de **relecture** d'une
interaction complète.

## 7. Alignement méta-modèle

- Les entrées sont horodatées et **tracées** (SCC-DOC-0016) ; append-only
  (SCC-DOC-0006) ; jamais de donnée RAW ni de secret (SCC-DOC-0022, SCC-DOC-0023).
- La mémoire est un **Module** distinct (un dépôt), sans couplage aux moteurs
  (SCC-DOC-0003, SCC-DOC-0008).
