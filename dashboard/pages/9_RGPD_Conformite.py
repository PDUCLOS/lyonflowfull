"""Page commune — RGPD & Conformité.

 (2026-06-17) — nettoyage :
* Bloc "Contact DPO" viré (email placeholder dpo@lyonflowfull.fr, pas de
  DPO nommé en prod — sera réintroduit quand un vrai DPO sera nommé).
* Section "Activité RGPD" (registre Article 30) virée : affiche "Aucun
  log d'audit disponible" tant que le schéma ``rgpd.audit_log`` n'est pas
  peuplé en prod. À recâbler quand l'implémentation sera complète.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.auto_refresh import setup_auto_refresh
from dashboard.components.data_status import render_data_status_banner
from dashboard.components.freshness_badge import render_freshness_badge
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.theme import inject_theme
from src.config import get_settings

st.set_page_config(
    page_title="RGPD — LyonFlowFull",
    page_icon="🔒",
    layout="wide",
)

inject_theme()
render_sidebar_navigation()
setup_auto_refresh()
render_freshness_badge()

st.title("🔒 RGPD & Conformité")
render_data_status_banner()

st.markdown(
    """
    ### Données traitées par LyonFlowFull

    LyonFlowFull est une plateforme **grand public** d'analyse de la mobilité
    sur la Métropole de Lyon. Elle traite uniquement des **données ouvertes**
    et **anonymisées**.

    | Source | Type | Finalité | Rétention |
    |--------|------|----------|-----------|
    | Grand Lyon (boucles, chantiers) | Open data public | Prédiction trafic | 7-45j (Bronze), 90j (Silver) |
    | Vélo'v GBFS | Open data public | Prédiction disponibilité stations | 14j |
    | TCL SIRI Lite | Open data public | Position bus/tram, calcul retard | 7j |
    | Open-Meteo | Open data public | Météo, qualité air | Pas de rétention long terme |
    | Open-Meteo Air Quality | Open data public | Indice pollution | Pas de rétention long terme |

    ### Données personnelles

    **LyonFlowFull ne collecte aucune donnée personnelle identifiante** :
    - Pas de compte utilisateur obligatoire
    - Pas d'historique de trajets nominatif
    - Pas de tracking publicitaire
    - Pas de partage avec des tiers

    Les espaces "Pro TCL" et "Élu" sont protégés par mot de passe
    (stocké en variable d'environnement, jamais en clair dans le code).
    Les logs d'accès sont anonymisés.

    ### Cookies

    Streamlit utilise des cookies techniques strictement nécessaires au
    fonctionnement de la session. Aucun cookie de tracking, aucun cookie
    publicitaire.

    ### Vos droits

    Conformément au RGPD, vous pouvez :
    - Demander l'accès à vos données (il n'y en a pas nominatives)
    - Demander la suppression (les comptes ne sont pas nominatifs)
    - Porter réclamation auprès de la CNIL
    """
)

st.divider()
st.caption(f"LyonFlowFull v{get_settings().app_version} — conforme RGPD")
