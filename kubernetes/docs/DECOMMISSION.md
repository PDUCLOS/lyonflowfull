# Decommissionnement VPS — Checklist

Une fois la migration VPS → K8s validee (cf `DEPLOY.md` etape 5), on arrête
le VPS proprement. Faire CHAQUE etape, dans l'ordre. Ne pas sauter de case.

## Pre-requis

- [ ] Migration data terminee (`./scripts/migrate-vps.sh` checksums OK)
- [ ] DNS bascule sur LB K8s depuis ≥ 7 jours
- [ ] Aucune erreur en prod K8s depuis 7 jours (Prometheus + logs)
- [ ] Tests de charge K8s passes (k6 200 VU, p95 < 1s)
- [ ] Backups K8s automatiques verifies (CronJob `postgres-backup` reussi 7j)
- [ ] Decision documentee dans `CHANGELOG.md`

## Etape 1 — Verification zero trafic VPS

```bash
# Sur VPS — nb requetes API derniere semaine
ssh vps "sudo journalctl -u lyonflow-api --since '7 days ago' | grep -c 'GET\|POST'"

# Doit etre ≤ qq dizaines (sondes monitoring seulement, pas de vrais users)
```

Si trafic > 100 req/jour : investiguer (DNS cache long, ancien client...).

## Etape 2 — Backup final VPS (cold storage)

```bash
# Dump complet
ssh vps "sudo -u postgres pg_dump -Fc lyonflow" > /Volumes/Backup/vps-final-$(date +%Y%m%d).dump

# Configs systeme
ssh vps "sudo tar -czf - /etc/lyonflow /opt/lyonflow /home/lyonflow/.env" \
  > /Volumes/Backup/vps-config-$(date +%Y%m%d).tar.gz

# Verifier les 2 fichiers
ls -lh /Volumes/Backup/vps-*-$(date +%Y%m%d).*
```

Chiffrer + envoyer offsite (Object Storage ou cle USB hors site).

## Etape 3 — Stop services VPS (graceful)

```bash
ssh vps "sudo systemctl stop lyonflow-api lyonflow-streamlit lyonflow-airflow"
ssh vps "sudo systemctl disable lyonflow-api lyonflow-streamlit lyonflow-airflow"
# Postgres en dernier : possibles connexions tardives
ssh vps "sudo systemctl stop postgresql"
```

## Etape 4 — Cleanup DNS

- Supprimer les A records pointant sur l'IP VPS (api-old, app-old)
- Verifier TTL < 1h
- Attendre propagation 24h avant etape suivante

## Etape 5 — Snapshot + arret VM

```bash
# Snapshot final via provider (OVH/Scaleway)
# Garder 30 jours en case rollback

# Stop VM (pas delete tout de suite)
# Via console provider
```

## Etape 6 — Periode d'observation (30 jours)

Pendant 30 jours :
- VM arretee mais snapshot conserve
- Backups cold storage conserves
- Re-check hebdo : trafic K8s OK, pas de regression

## Etape 7 — Suppression definitive (J+30)

Quand tout OK depuis 30j :

```bash
# Delete VM (provider console)
# Delete IP publique
# Delete domaines / sous-domaines obsoletes
```

Garder le snapshot final OFFLINE 1 an pour audit / RGPD.

## Etape 8 — Mise a jour docs

- [ ] `README.md` : retirer mention VPS
- [ ] `docs/DEPLOYMENT.md` : remplacer par `kubernetes/docs/DEPLOY.md`
- [ ] `CHANGELOG.md` : ajouter section `[0.5.0] - Migration K8s definitive`
- [ ] `CLAUDE.md` (project memory) : marquer Phase 2 = production active

## Etape 9 — Branche `vps` Git

La branche `vps` du repo reste en l'etat (archive Phase 1). Tagger :

```bash
git checkout vps
git tag v0.3.1-vps-final -m "Derniere version VPS avant decommission"
git push origin v0.3.1-vps-final
```

La branche peut ensuite etre archivee mais pas supprimee (historique projet).
