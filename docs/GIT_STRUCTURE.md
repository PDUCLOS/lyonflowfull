# Structure Git — LyonFlow

Ce repo utilise **4 branches longues** correspondant aux 3 phases du
projet + une branche fixe d'archive VPS.

## Vue d'ensemble

```
                         v0.3.0 (init Phase 1)
                              │
                              ▼
                       ┌─────────────┐
                       │   main      │  ←── pointeur Phase 1 + fixes
                       └──────┬──────┘
              ff (read-only)  │
                  ┌───────────┼───────────────┐
                  ▼           ▼ merge          ▼ merge
            ┌──────────┐  ┌──────────┐  ┌───────────────┐
            │   vps    │  │kubernetes│  │  cloud-demo   │
            │  Phase 1 │  │ Phase 2  │  │   Phase 3     │
            │ (snapshot│  │  (K8s)   │  │ (Jedha demo)  │
            │  prod)   │  │          │  │               │
            └──────────┘  └─────┬────┘  └───────────────┘
                                │
                                └── base utilisee par cloud-demo
```

## Mapping branches ↔ phases (CLAUDE.md / project memory)

| Branche | Phase | Statut | Cible deploiement |
|---------|-------|--------|-------------------|
| `main` | Phase 1 + fixes | active | reference + dev |
| `vps` | Phase 1 frozen | archive | VPS actuel (51.83.159.224) |
| `kubernetes` | Phase 2 | manifests prets | Cluster K8s production |
| `cloud-demo` | Phase 3 | overlay pret | Scaleway Kapsule ephemere |

## Conventions

### Workflow merge

```
main (fixes pipeline)
  ├── ff-merge → vps  (Phase 1 frozen, garde dernier etat stable VPS)
  └── merge   → kubernetes  (Phase 2 herite des fixes Phase 1)
        └── inherit base → cloud-demo (extends kubernetes/base)
```

**Regles** :
- `main` recoit les fixes pipeline (bug, refacto, secu)
- `vps` est fast-forward depuis main quand on veut updater le VPS
- `kubernetes` merge main pour propager les fixes dans les manifests
- `cloud-demo` extends `kubernetes/base` via Kustomize : pas besoin de
  merger main systematiquement, juste rebase si conflit Kustomize

### Tags

| Pattern | Usage | Exemple |
|---------|-------|---------|
| `v0.X.Y` | Release main | `v0.3.0`, `v0.3.1` |
| `v0.X.Y-vps` | Snapshot VPS deploy | `v0.3.1-vps`, `v0.3.1-vps-final` |
| `v0.X.Y-k8s` | Release K8s manifests | `v0.4.0-k8s` |
| `v0.X.Y-demo` | Cluster demo Jedha | `v0.5.0-demo-jedha-2026-09-15` |

### Branches courtes (feature branches)

Toujours partir de la branche cible :

```bash
# Fix dans le pipeline Phase 1
git checkout main && git checkout -b fix/silver-to-gold-nplus1

# Manifest K8s
git checkout kubernetes && git checkout -b feat/k8s-redis-cluster

# Demo
git checkout cloud-demo && git checkout -b feat/demo-pitch-update
```

Convention nommage : `<type>/<scope>-<short-desc>`
- `feat` / `fix` / `chore` / `docs` / `refactor` / `test`

PRs mergees en **squash** sur la branche cible (historique propre).

## Commands courantes

```bash
# Liste des branches et leur tracking
git branch -vv

# Quel commit suis-je et sur quelle branche
git log -1 --oneline --decorate

# Switcher entre phases
git checkout main         # Phase 1 reference
git checkout vps          # Phase 1 frozen
git checkout kubernetes   # Phase 2 K8s
git checkout cloud-demo   # Phase 3 demo

# Propager un fix de main vers les branches phase 2/3
git checkout kubernetes && git merge main
git checkout cloud-demo  && git merge kubernetes
```

## Historique des commits cles

| Commit | Branche | Description |
|--------|---------|-------------|
| `0fc687a` | main, vps | Phase 1 initial (Sprints 1-7, v0.3.0) |
| `4b3c079` | main, vps | Fix bugs pipeline (vacances, N+1, doublon) |
| `d4a3ecf` | kubernetes | K8s foundation (postgres, redis, fastapi, streamlit, ...) |
| `5021b88` | kubernetes | Merge main → kubernetes (propage fixes pipeline) |
| `846d855` | kubernetes | Phase 2 complete (monitoring, GPU, Dockerfiles, charge) |
| `c8ebe62` | cloud-demo | Phase 3 Jedha (Terraform + overlay + scripts demo) |

## CI/CD par branche

| Branche | Workflow GitHub Actions | Trigger |
|---------|------------------------|---------|
| `main` | `.github/workflows/ci.yml` | push : lint+tests+docker+Trivy |
| `vps` | Aucun (snapshot read-only) | — |
| `kubernetes` | `.github/workflows/k8s-images.yml` | push : build ghcr images |
| `cloud-demo` | (TODO) | trigger manuel spin-up.sh |

## Remote

Tout sur `origin = https://github.com/PDUCLOS/lyonflowfull.git`.
Pas de fork separe : un seul repo, plusieurs branches.

## FAQ

**Q : Pourquoi pas un monorepo / multi-repos ?**
R : Multi-branches est plus simple a maintenir : meme historique, meme
issues GitHub, meme CI shared. Les overlays Kustomize partagent la base
sans duplication de code.

**Q : Comment garder `vps` a jour ?**
R : `git checkout vps && git merge main --ff-only && git tag v0.X.Y-vps`.
Le `--ff-only` garantit que vps reste un superset lineaire de main.

**Q : Que faire si conflit lors du merge main → kubernetes ?**
R : Resoudre dans `kubernetes/base/*.yaml` en priorisant la version
kubernetes (les manifests sont specifiques). Les conflits sur
`src/`, `dags/` se resolvent en gardant main (la branche est la
reference du code).

**Q : La branche `cloud-demo` n'a-t-elle pas trop divergee ?**
R : Non, elle ajoute uniquement `cloud-demo/` et n'edite jamais les
fichiers de `kubernetes/base`. Pas de risque de drift code.
