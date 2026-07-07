# Architecture de la mémoire BrainAI

## 1. Position dans SCC

BrainAI Memory (`11`) est la **mémoire d'expérience** du Kernel BrainAI (`10`). Elle
observe et conserve ce que le Kernel *vit*, sans le modifier et sans empiéter sur
SCC_MEMORY (`05`, objets cognitifs).

```
   Kernel BrainAI (10) ── handle(query) -> réponse publique (dict)
        │  (sortie publique, aucune modification du Kernel)
   ▶ BrainAI Memory (11) ── KernelRecorder -> BrainMemoryStore
        │
   data/brain_memory.jsonl (append-only, chaîné)  +  brain_sessions.jsonl
```

## 2. Deux mémoires, deux responsabilités

| Mémoire | Conserve | Responsabilité |
|---------|----------|----------------|
| **SCC_MEMORY (05)** | objets cognitifs (issus des sources) | savoir du système |
| **BrainAI Memory (11)** | expérience du Kernel (demandes, plans, décisions…) | vécu de l'orchestrateur |

Aucune duplication : les deux ne stockent pas les mêmes objets et ne partagent
aucun code.

## 3. Flux d'écriture contrôlée

```
mémorable (Event/Preference/Learning/Trace)
   │
   ├─ Redactor.scrub()      # confidentialité : secrets & RAW -> [REDACTED]
   ├─ enveloppe MemoryEntry # id séquentiel, horodatage (horloge injectée), tags
   ├─ finalize(prev_hash)   # chaîne d'empreintes (tamper-evident)
   ├─ index.add()           # recherche
   ├─ rattachement session  # continuité
   └─ append JSONL          # persistance append-only
```

## 4. Composants

```
core/       config (as_of figé) · errors · clock (déterministe) · model
privacy     Redactor (garde-fous confidentialité)
index       MemoryIndex (recherche)
retention   RetentionPolicy (purge protégée)
audit       chaîne d'empreintes + confidentialité résiduelle
report      rapport de mémoire (JSON + Markdown)
store       BrainMemoryStore (façade : write/search/export/audit/retention/report)
recorder    KernelRecorder / RecordingKernel (intégration non invasive)
cli         scc-brain-memory
```

## 5. Déterminisme

Horloge injectable (`FixedClock` par défaut, `as_of` figé), identifiants
séquentiels, sérialisation canonique, itérations triées, empreintes SHA-256. Deux
enregistrements identiques produisent une mémoire **strictement identique**
(vérifié).

## 6. Invariants tenus

| Invariant | Comment |
|-----------|---------|
| Aucun moteur/Runtime/API/Control Plane/Kernel modifié | consomme la sortie publique du Kernel |
| Aucun secret / RAW stocké | caviardage systématique (`Redactor`) |
| Auditable & traçable | chaîne d'empreintes + audit intégrité/confidentialité |
| Purge / export / audit prévus | `RetentionPolicy`, `export_*`, `audit()` |
| Aucun LLM / réseau / dépendance externe | stdlib pur |
| Déterminisme maximal | horloge injectée + règles pures |
