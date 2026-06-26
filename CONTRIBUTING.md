# Contributing à LyonFlow

Merci de votre intérêt pour contribuer à LyonFlow ! 🎉

## Code de conduite

Ce projet adhère à un code de conduite. En participant, vous vous engagez à
respecter ses termes.

## Comment contribuer

### Signaler un bug

1. Vérifiez que le bug n'a pas déjà été signalé (issues GitHub)
2. Créez une issue avec :
   - Description claire
   - Étapes pour reproduire
   - Comportement attendu vs observé
   - Captures d'écran si pertinent
   - Environnement (OS, Python, Docker, etc.)

### Proposer une fonctionnalité

1. Ouvrez une issue "Feature request" avec :
   - Cas d'usage
   - Bénéfice attendu
   - API/UI proposée

### Soumettre une Pull Request

1. Fork le repo
2. Créez une branche : `git checkout -b feature/ma-feature`
3. Committez avec un message clair : `git commit -m "feat: ma feature"`
4. Poussez : `git push origin feature/ma-feature`
5. Ouvrez une PR

## Standards de code

### Python
- Python 3.12+
- Type hints partout
- Docstrings pour les fonctions publiques
- Ruff lint (`make lint`)
- Mypy (non bloquant, `make typecheck`)

### SQL
- **TOUJOURS** paramétré : `cur.execute(query, params)`
- **JAMAIS** de f-string SQL
- snake_case pour les noms de table/colonnes
- Index sur les colonnes WHERE/JOIN

### Tests
- pytest pour chaque nouvelle feature
- Un test = un comportement
- Mock les appels API externes
- Coverage > 80% pour le nouveau code

### Commits

Format [Conventional Commits](https://www.conventionalcommits.org/fr/) :
- `feat: nouvelle fonctionnalité`
- `fix: correction de bug`
- `docs: documentation uniquement`
- `refactor: refactoring sans changement fonctionnel`
- `test: ajout de tests`
- `chore: maintenance (deps, config)`

### Branches
- `main` : production
- `develop` : intégration
- `feature/xxx` : nouvelle fonctionnalité
- `fix/xxx` : correction de bug
- `release/x.y.z` : préparation release

## Workflow de review

1. CI doit passer (lint, tests, build)
2. Au moins 1 review approuvée
3. Pas de conflit avec main
4. Tests E2E si feature UI

## Sécurité

Pour signaler une vulnérabilité : **security@lyonflow.fr**
Ne pas ouvrir d'issue publique.

## Licence

En contribuant, vous acceptez que vos contributions soient sous licence MIT.
