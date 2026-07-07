# Garde-fous de confidentialité

> **Règle absolue** : la mémoire BrainAI ne stocke **jamais** de secret, token, mot
> de passe ni **donnée RAW**. Aucune exception.

## 1. Caviardage systématique à l'écriture

Toute écriture passe par le `Redactor` **avant** persistance. Rien n'entre en
mémoire sans être nettoyé.

## 2. Ce qui est caviardé

| Cible | Règle | Résultat |
|-------|-------|----------|
| **Clés sensibles** | `password`, `token`, `api_key`, `secret`, `authorization`, `bearer`, `private_key`, `credentials`, `cookie`, `ssn`, `card`, `cvv`… | valeur → `[REDACTED]` |
| **Clés RAW** | `raw`, `raw_data`, `raw_content`, `blob`, `binary` | valeur → `[REDACTED]` |
| **Valeurs-secrets** | motifs : `sk-…`, tokens GitHub `ghp_…`, `Bearer …`, JWT `eyJ…`, longues empreintes hex, clés AWS `AKIA…` | valeur → `[REDACTED]` |
| **Chaînes trop longues** | > 2000 caractères (anti-dump / anti-RAW) | tronquée + `…[TRUNCATED]` |

Le caviardage est **récursif** (dictionnaires, listes) et **déterministe**. Une
entrée caviardée porte `redacted: true` (traçabilité du fait).

## 3. Clés conservées, valeurs masquées

Une clé sensible **peut rester** (ex. `password`) mais sa **valeur est toujours
`[REDACTED]`**. Cela préserve la structure/traçabilité sans jamais exposer le secret.

## 4. Contrôle d'audit de confidentialité

`audit()` re-scanne toutes les entrées : il ne signale que les **secrets non
caviardés résiduels**. Une valeur déjà `[REDACTED]` n'est **pas** un défaut. Sur une
mémoire saine, `privacy.ok = true` et `offending = []`.

## 5. Vérifié par les tests

- un secret (`password`, `sk-…`) est caviardé à l'écriture ;
- une clé RAW est refusée (caviardée) ;
- l'export **ne contient jamais** la valeur secrète (`"hunter2" not in export`) ;
- l'audit de confidentialité passe sur une mémoire saine.

## 6. Portée

Ces garde-fous s'appliquent à **toutes** les sources d'écriture, y compris
l'ingestion de la réponse publique du Kernel : si une demande utilisateur contenait
un secret, il serait caviardé avant mémorisation.
