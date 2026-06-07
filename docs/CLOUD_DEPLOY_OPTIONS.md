# Options cloud pour démo Jedha (Phase 3)

> **Date** : 2026-06-06
> **Statut** : préparation — pas de déploiement cloud tant que l'utilisateur
> n'a pas pris de décision et fourni l'accès.
> **Trigger** : certification RNCP 38777 Jedha + besoin de démo publique.

## 🎯 Objectif Phase 3

Rendre LyonFlowFull accessible publiquement sur Internet pour :

* **Démonstration certification Jedha** (jury + public)
* **Validation utilisateur** (quelques centaines de visiteurs pendant la démo)
* **Scalabilité ponctuelle** (pics le jour J)

## 📊 Comparatif providers

### 1. Scaleway (recommandé pour la France)

| Critère | Détail |
|---------|--------|
| Datacenter | Paris (DC5), Amsterdam |
| GPU | GPU T4 / L4 disponible |
| Kubernetes managé | Kapsule (5€/mois base) |
| Stockage objet | S3-compatible (1€/mois pour 75 GB) |
| Prix LyonFlowFull | ~50-80 €/mois (K8s + DB + storage) |
| RGPD | ✅ 100% UE |
| Support | Français, bon |
| Crédits startup | 500€ offerts à l'inscription |
| Délai setup | 1-2 heures |

**Verdict** : **meilleur choix pour la démo Jedha**. RGPD ++, prix bas,
France. Le panel Jedha apprécie les solutions souveraines.

### 2. OVHcloud

| Critère | Détail |
|---------|--------|
| Datacenter | Roubaix, Strasbourg, Gravelines |
| GPU | GPU T4 / V100 disponible |
| Kubernetes managé | OVH Kubernetes (gratuit control plane) |
| Stockage objet | S3-compatible (1,99€/mois pour 75 GB) |
| Prix LyonFlowFull | ~60-90 €/mois |
| RGPD | ✅ 100% UE |
| Support | Français, très bon |
| Crédits startup | Programme "Startup program" |
| Délai setup | 1-2 heures |

**Verdict** : alternative solide à Scaleway, légèrement plus cher mais
avec un track record plus long sur l'hébergement critique.

### 3. Hetzner

| Critère | Détail |
|---------|--------|
| Datacenter | Falkenstein (DE), Helsinki (FI), Ashburn (US) |
| GPU | Pas de GPU managé (mais servers avec GPU dispo) |
| Kubernetes managé | Pas (clusters managés non dispo) |
| Stockage objet | S3-compatible (S3 Hetzner, très bon marché) |
| Prix LyonFlowFull | ~30-50 €/mois (VPS + storage) |
| RGPD | ✅ UE |
| Support | Allemand/anglais, bon |
| Crédits startup | Pas |
| Délai setup | 2-3 heures (self-managed) |

**Verdict** : le moins cher, mais il faut self-manage K8s. Pas idéal
pour une démo Jedha où on veut focus sur l'appli.

### 4. Google Cloud (GKE)

| Critère | Détail |
|---------|--------|
| Datacenter | europe-west1 (Belgium), europe-west3 (Frankfurt) |
| GPU | T4/L4/A100 disponible |
| Kubernetes managé | GKE Autopilot (15€/node/mois minimum) |
| Stockage objet | GCS, ~3$/mois pour 100 GB |
| Prix LyonFlowFull | ~150-300 €/mois (cher) |
| RGPD | ⚠️ Adequacy decision UE, pas 100% souverain |
| Support | Excellent, mais 24h+ pour les incidents |
| Crédits startup | $300 pendant 90 jours |
| Délai setup | 2-4 heures (IAM + quotas) |

**Verdict** : overkill pour la démo Jedha. Pertinent si on vise
scalabilité enterprise.

### 5. AWS (EKS)

| Critère | Détail |
|---------|--------|
| Datacenter | eu-west-1 (Ireland), eu-central-1 (Frankfurt) |
| GPU | Tous modèles |
| Kubernetes managé | EKS (73$/mois/cluster minimum) |
| Stockage objet | S3 (~3$/mois) |
| Prix LyonFlowFull | ~200-400 €/mois (très cher) |
| RGPD | ⚠️ Schrems II problématique pour certaines données |
| Support | Premium hors de prix |
| Crédits startup | AWS Activate ($1000+) |
| Délai setup | 4-8 heures (config lourde) |

**Verdict** : pas adapté. AWS est cher et la conformité RGPD est un
sujet juridique pour Jedha.

## 🎯 Recommandation finale

### Pour la démo Jedha : **Scaleway Kapsule**

* **Pourquoi** : prix, RGPD, France, support FR, crédits startup
* **Combien** : ~60 €/mois
* **Setup** : 1-2 heures via leur console
* **Domaine** : `demo.lyonflow.fr` (DNS Scaleway ou OVH)
* **SSL** : Let's Encrypt via cert-manager
* **Monitoring** : Scaleye (gratuit) + Grafana Cloud (free tier)

### Pour la migration K8s : voir K8S_MIGRATION_PLAN.md

### Pour la certification RNCP 38777 (Jedha) :

Le jury évalue :

1. **Architecture technique** (Kubernetes, MLflow, ML)
2. **Méthodologie MLOps** (Medallion, quality gates, drift)
3. **Code qualité** (tests, CI/CD, sécurité)
4. **Documentation** (lisibilité, complétude)
5. **Démo live** (stabilité, performance, UX)

→ **Scaleway Kapsule + cette doc stack + le rapport de certification**
couvrent tous les points.

## 💰 Budget consolidé pour Phase 3

| Poste | Prix/mois | Année |
|-------|-----------|-------|
| Scaleway Kapsule (3 nodes STARDUST) | 48 € | 576 € |
| Block storage 100 GB | 2 € | 24 € |
| Object Storage 50 GB (backups) | 1 € | 12 € |
| Load balancer | 5 € | 60 € |
| Domaine `lyonflow.fr` (OVH) | – | 12 €/an |
| Certificats SSL (Let's Encrypt) | 0 € | 0 € |
| Monitoring Scaleye (free tier) | 0 € | 0 € |
| Grafana Cloud (free tier) | 0 € | 0 € |
| **Total mensuel** | **~57 €** | **684 €/an** |

Crédits startup Scaleway : **500€ offerts** = couvre ~9 mois.

## 📅 Timeline recommandée

| Date | Action |
|------|--------|
| 2026-07-15 | Validation choix provider (Scaleway par défaut) |
| 2026-07-20 | Création compte Scaleway + demande crédits startup |
| 2026-08-01 | Setup Kapsule (cf. K8S_MIGRATION_PLAN.md) |
| 2026-08-15 | Migration données depuis VPS |
| 2026-09-01 | Tests de charge + sécurité |
| 2026-09-15 | URL publique + démo interne |
| 2026-10-01 | **Démo certification Jedha RNCP 38777** |
| 2026-10-15 | Bilan + archivage (si pas de suite) |

## 📌 TODO utilisateur (à fournir)

* [ ] Validation choix : **Scaleway** (par défaut) ou autre ?
* [ ] Compte Scaleway créé + email de demande crédits startup
* [ ] Nom de domaine `lyonflow.fr` (sinon `lyonflowfull.scaleway.com` en MVP)
* [ ] Validation budget ~60 €/mois
* [ ] Date démo Jedha confirmée (pour respecter la timeline)

Une fois ces 5 points OK, le sprint de mise en production peut démarrer
(~1-2 semaines pour Scaleway Kapsule complet).
