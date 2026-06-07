# LyonFlowFull — Phase 3 Cloud Demo Jedha

Deploiement ephemere pour soutenance RNCP 38777 Jedha (Architecte IA).
Provider : **Scaleway Kapsule** (Paris DC5, RGPD ++).
Strategie : cluster lance 2-4h pour soutenance, supprime apres.

## Pourquoi ephemere

| Critere | Permanent | Ephemere (choisi) |
|---------|-----------|-------------------|
| Cout / mois | ~57 € | ~2 € (4h de demo) |
| Risque facture | Surveillance permanente | Zero (spin-up/tear-down scripts) |
| Data | Live pipeline | Pre-seed Lyon 7j |
| Demo | Tout dispo | Tout dispo + GPU si voulu |

Budget total certif : ~10 € (3 repetitions + soutenance).

## Architecture

```
cloud-demo/
├── overlays/jedha-demo/    # Kustomize overlay (extends kubernetes/base)
│   ├── kustomization.yaml
│   └── patches/             # 1 replica, host jedha-demo, mock data
├── terraform/               # Provisioning Scaleway (cluster + LB + DNS)
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── scripts/
│   ├── spin-up.sh           # terraform apply + bootstrap + seed + deploy
│   ├── tear-down.sh         # delete cluster + LB + DNS (zero residu)
│   └── seed-demo-data.sh    # SQL seed 7j historique Lyon mock
└── docs/
    ├── SOUTENANCE_RNCP_38777.md   # Story demo + slides outline + URLs
    └── DEMO_SCRIPT.md             # Pas-a-pas demo 20 min
```

## Workflow demo

```bash
# T-2h avant soutenance
cd cloud-demo
./scripts/spin-up.sh
# → cluster pret, https://lyonflow.demo.jedha.fr UP, data 7j seeded

# Pendant soutenance
# (utiliser docs/DEMO_SCRIPT.md)

# T+30min apres soutenance
./scripts/tear-down.sh
# → cluster delete, LB delete, DNS clean, facturation arretee
```

## Couts estimes (par session 4h)

| Ressource | Quantite | Cout/h | Cout 4h |
|-----------|----------|--------|---------|
| Kapsule control plane | 1 | 0 € | 0 € |
| Node POP2-2C-8G | 2 | 0,05 € | 0,40 € |
| Load Balancer | 1 | 0,01 € | 0,04 € |
| Object Storage | 5 GB | ~0 € | ~0 € |
| Traffic sortant | < 1 GB | 0 € | 0 € |
| **Total** | | | **~0,45 €** |

GPU optionnel (node g5-xs T4) : +1 €/h → 4 € pour la demo.

## Pre-requis user

- [ ] Compte Scaleway active (carte CB)
- [ ] Token API Scaleway (scope organisation)
- [ ] Domaine `*.demo.jedha.fr` (ou autre) + DNS gerable
- [ ] Terraform 1.7+ installe localement
- [ ] kubectl + kustomize + helm (cf kubernetes/docs/DEPLOY.md)
