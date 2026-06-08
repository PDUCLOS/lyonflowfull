"""Page commune — RGPD & Conformité.

Sprint 6 — binding DB :
* Section "Activité RGPD" lit directement ``rgpd.audit_log``,
  ``rgpd.user_consents``, ``rgpd.data_subject_requests`` via data_loader.
* Si DB down → fallback mock transparent.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.data_status import render_data_status_banner
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.theme import inject_theme
from src.data.data_loader import (
    load_rgpd_audit,
    load_rgpd_consents,
)

st.set_page_config(
    page_title="RGPD — LyonFlowFull",
    page_icon="🔒",
    layout="wide",
)

inject_theme()
render_sidebar_navigation()

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

    ### Contact DPO

    Pour toute question RGPD : **dpo@lyonflowfull.fr**
    """
)

st.divider()
st.markdown("### 📊 Activité RGPD (registre Article 30 — données temps réel)")

# Consents summary
consents_df = load_rgpd_consents(force_mock=False)
if not consents_df.empty:
    cols = st.columns(len(consents_df))
    for col, (_, row) in zip(cols, consents_df.iterrows()):
        with col:
            granted_pct = (row["granted_count"] / row["total"] * 100) if row["total"] else 0
            st.metric(
                label=row["consent_type"],
                value=f"{int(row['granted_count'])} / {int(row['total'])}",
                delta=f"{granted_pct:.0f}% acceptation",
                delta_color="normal" if granted_pct >= 50 else "inverse",
            )

# Audit log
audit_df = load_rgpd_audit(limit=50)
if not audit_df.empty:
    st.markdown("##### 🔍 Dernières actions (audit log)")
    # Cacher IP complete par défaut (RGPD)
    display_df = audit_df.copy()
    if "ip_address" in display_df.columns:
        display_df["ip_address"] = display_df["ip_address"].astype(str).str.replace(r"\.\d+$", ".xxx", regex=True)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.info("Aucun log d'audit disponible — DB non connectée ou table vide.")

st.divider()
st.caption("LyonFlowFull v0.1.0 — conforme RGPD")
