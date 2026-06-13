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

<<<<<<< HEAD
=======
# Sprint VPS-6 (2026-06-11) — Vérifie que la politique "zéro mock" est
# activée sur le VPS : LYONFLOW_DEMO_MODE doit être présent et valoir 0.
# Les mocks sont INTERDITS en production. Le mode démo est réservé au
# dev local (LYONFLOW_DEMO_MODE=1).
DEMO_MODE_VAL=$(grep -E "^LYONFLOW_DEMO_MODE=" "$DEPLOY_ENV" | cut -d= -f2 || echo "")
if [ -z "$DEMO_MODE_VAL" ]; then
    echo "[WARN] LYONFLOW_DEMO_MODE absent de $DEPLOY_ENV — fallback par défaut (0 = prod)."
    echo "       Pour lever l'ambiguïté, ajouter explicitement : LYONFLOW_DEMO_MODE=0"
elif [ "$DEMO_MODE_VAL" != "0" ]; then
    echo "[ERROR] LYONFLOW_DEMO_MODE=$DEMO_MODE_VAL (attendu: 0 = prod)."
    echo "         Le mode démo (LYONFLOW_DEMO_MODE=1) est INTERDIT en production."
    echo "         Voir docs/PLAN_NO_MOCK_VPS.md pour la politique fail loud."
    exit 1
fi

>>>>>>> origin/main
echo "[OK] Toutes les variables critiques sont configurées."
