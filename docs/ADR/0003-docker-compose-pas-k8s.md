# ADR-0003 : Docker Compose avant Kubernetes

## Statut
Accepté (2026-06-06)

## Contexte
Le projet doit tourner sur 1 VPS unique. 3 options :
1. Bare metal (systemd services)
2. **Docker Compose** ✅
3. Kubernetes (k3s ou managé)

## Décision
Docker Compose pour la Phase 1, K8s évalué en Phase 2.

## Rationale
- 1 serveur = pas besoin d'orchestration multi-node
- Compose = 1 fichier YAML, simple
- K8s = 500% complexité pour 0% valeur à cette échelle
- Migration path vers K8s possible si scale

## Métriques VPS
- 6 CPU
- 12 GB RAM
- 100 GB SSD
- Trafic estimé : < 1000 req/jour

## Si migration K8s
Quand (et seulement si) :
- Multi-node (> 3 serveurs)
- > 10 000 req/jour soutenu
- Équipe DevOps > 2 personnes

Outils : kompose (migrer docker-compose) + manifests Kustomize
