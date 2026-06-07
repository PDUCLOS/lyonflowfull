# ADR Index

Liste des Architecture Decision Records du projet LyonFlowFull.

| N° | Titre | Statut | Date |
|----|-------|--------|------|
| 0001 | [Architecture Medallion (Bronze/Silver/Gold)](0001-architecture-medallion.md) | ✅ Accepté | 2026-06-06 |
| 0002 | [3 personas en 1 dashboard](0002-3-personas-1-dashboard.md) | ✅ Accepté | 2026-06-06 |
| 0003 | [Docker Compose avant Kubernetes](0003-docker-compose-pas-k8s.md) | ✅ Accepté | 2026-06-06 |
| 0004 | [psycopg2 pur (pas de Polars) dans Airflow](0004-psycopg2-pur-pas-polars.md) | ✅ Accepté | 2026-06-06 |

## Convention de nommage

`NNNN-titre-court-en-kebab-case.md`

## Template

```markdown
# ADR-NNNN : Titre

## Statut
Proposé | Accepté | Déprécié | Remplacé par NNNN

## Contexte
Quel problème / décision ?

## Décision
Ce qu'on a choisi.

## Conséquences
Positives, négatives, neutres.

## Alternatives écartées
Pourquoi pas les autres options.
```

## Quand écrire un ADR

- Nouveau service / nouveau schéma
- Nouveau framework / nouvelle lib
- Décision structurante (auth, deploy, observabilité)
- Sprint 0 / début de projet
