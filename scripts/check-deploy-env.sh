#!/bin/bash
# =============================================================================
# scripts/check-deploy-env.sh — Vérification pré-déploiement VPS
# =============================================================================
# Sprint VPS-1 : s'assurer que .deploy.env a les bonnes permissions (chmod 600)
# avant tout rsync vers le VPS. Évite d'envoyer un fichier lisible par tous.
# =============================================================================
set -euo pipefail

DEPLOY_ENV="${1:-.deploy.env}"

if [ ! -f "$DEPLOY_ENV" ]; then
    echo "[ERROR] Fichier $DEPLOY_ENV introuvable."
    echo "Copie .deploy.env.example : cp .deploy.env.example $DEPLOY_ENV"
    exit 1
fi

# Permissions actuelles
PERMS=$(stat -f "%A" "$DEPLOY_ENV" 2>/dev/null || stat -c "%a" "$DEPLOY_ENV" 2>/dev/null)

if [ "$PERMS" != "600" ]; then
    echo "[WARN] $DEPLOY_ENV a les permissions $PERMS (attendu: 600)"
    echo "Fix : chmod 600 $DEPLOY_ENV"
    read -p "Appliquer chmod 600 maintenant ? [y/N] " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        chmod 600 "$DEPLOY_ENV"
        echo "[OK] Permissions corrigées : 600"
    else
        echo "[ABORT] Permissions non corrigées, déploiement annulé."
        exit 1
    fi
else
    echo "[OK] $DEPLOY_ENV a les bonnes permissions (600)"
fi

# Vérifie que les variables clés ne sont pas les valeurs par défaut
for var in VPS_HOST VPS_SSH_KEY VPS_DEPLOY_PATH DEPLOY_BRANCH; do
    val=$(grep -E "^${var}=" "$DEPLOY_ENV" | cut -d= -f2 || echo "")
    if [ -z "$val" ] || [[ "$val" == VOTRE_* ]] || [[ "$val" == *example* ]]; then
        echo "[ERROR] $var non configuré dans $DEPLOY_ENV (valeur: '$val')"
        exit 1
    fi
done

# Sprint P1.3 (2026-06-14) — Vérifie que l'aide démo n'est PAS visible en prod.
# Le .env est rsync sur le VPS ; si LYONFLOW_DEMO_AUTH_HELPER_VISIBLE=1 sur
# le VPS, l'UI affiche le mot de passe demo2026 en clair (cf. AUDIT § 2.3.1).
if [ -f ".env" ]; then
    DEMO_VISIBLE=$(grep -E "^LYONFLOW_DEMO_AUTH_HELPER_VISIBLE=" .env | cut -d= -f2 | tr -d '"' | tr -d "'" || echo "")
    if [ "$DEMO_VISIBLE" = "1" ]; then
        echo "[WARN] LYONFLOW_DEMO_AUTH_HELPER_VISIBLE=1 détecté dans .env"
        echo "       → l'aide démo affichera le mot de passe en clair sur le VPS."
        echo "       Pour la prod, mettre LYONFLOW_DEMO_AUTH_HELPER_VISIBLE=0 dans .env"
        read -p "Continuer quand même ? [y/N] " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "[ABORT] Déploiement annulé."
            exit 1
        fi
    fi
fi

echo "[OK] Toutes les variables critiques sont configurées."
