# Rétention & audit

## 1. Audit d'intégrité (chaîne d'empreintes)

Chaque entrée est **chaînée** à la précédente : `hash = SHA-256(contenu ‖
prev_hash)`. `audit()` recalcule la chaîne et vérifie chaque maillon.

```json
{ "ok": true,
  "integrity": { "ok": true, "count": 16, "first_broken": null },
  "privacy":   { "ok": true, "offending": [] } }
```

- **Falsification détectée** : modifier une entrée casse son `hash` et rompt la
  chaîne → `integrity.ok = false`, `first_broken = <id>` (vérifié par test).
- **Tamper-evident** : on ne peut ni altérer ni réordonner sans que l'audit le voie.

## 2. Politique de rétention

Deux règles **optionnelles**, désactivées par défaut (`null` = illimité) :

| Règle | Effet |
|-------|-------|
| `max_age_days` | purge les entrées plus anciennes que `as_of − N jours` |
| `max_entries_per_kind` | ne garde que les N plus récentes de chaque genre |

**Genres protégés** (`protected_kinds`, défaut `learning` + `preference`) : **jamais
purgés automatiquement** — l'apprentissage et les préférences sont durables.

## 3. Purge = opération auditée

`apply_retention()` :

1. calcule les entrées à conserver / purger (déterministe) ;
2. **compacte** le journal et **re-chaîne** les entrées conservées (la chaîne reste
   cohérente après purge) ;
3. réécrit le fichier et **journalise** un événement `retention` documentant le
   nombre purgé et la politique appliquée.

Ainsi la purge est **traçable** : la mémoire garde la preuve qu'une purge a eu lieu,
sans conserver les données purgées.

```json
{ "purged": 4, "kept": 3, "ids_purged": ["mem_…"], "policy": {…} }
```

## 4. Export & traçabilité

- `export --format json` : dump complet (config, sessions, entrées, audit).
- `export --format md` : rapport lisible.
- Les exports **héritent du caviardage** : aucun secret n'y figure jamais.

## 5. Rapport de mémoire

`report()` synthétise : totaux (entrées, sessions, caviardées), répartition par
genre/sous-type, période couverte, apprentissages/préférences/traces, et l'état
d'**intégrité** et de **confidentialité**. Persistable en JSON + Markdown via
`write_report()`.
