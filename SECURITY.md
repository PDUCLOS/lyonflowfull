# Security Policy

## Versions supportées

| Version | Supportée        |
|---------|------------------|
| 0.1.x   | ✅ Active        |
| < 0.1   | ❌ EOL           |

## Signaler une vulnérabilité

**Ne pas** ouvrir d'issue publique pour les vulnérabilités de sécurité.

Email : **security@lyonflowfull.fr**

Inclure :
- Description de la vulnérabilité
- Étapes pour reproduire
- Impact potentiel
- Versions affectées
- Solution proposée (optionnel)

Réponse sous 48h ouvrées.

## Bonnes pratiques

### Pour les développeurs

- **JAMAIS** de credentials en dur dans le code
- **TOUJOURS** SQL paramétré (`%s` psycopg2)
- **TOUJOURS** valider les inputs utilisateur
- **JAMAIS** logger de données sensibles (PII, mots de passe, tokens)
- Containers Docker **non-root** (USER appuser)
- **TOUJOURS** hasher les IP/UA avant stockage (RGPD)
- bcrypt pour les mots de passe (coût ≥ 12)

### Pour les déployeurs

- **TOUJOURS** changer les secrets par défaut avant prod
- **TOUJOURS** HTTPS (Let's Encrypt) en prod
- **JAMAIS** exposer les ports internes (5432, 9000) publiquement
- **TOUJOURS** backup automatisé (cron + monitoring)
- SSH key only (password auth désactivé)
- Firewall : uniquement 22, 80, 443

### Outils de scan

- `bandit` — analyse statique Python
- `pip-audit` — vulnérabilités deps
- `gitleaks` — secrets en dur
- `trivy` — scan images Docker

## Changelog sécurité

### 0.1.0 (2026-06-06)
- Initial release
- Aucun CVE connu
