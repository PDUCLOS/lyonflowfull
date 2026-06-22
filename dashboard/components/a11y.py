"""Helpers accessibilité (RGAA / WCAG 2.1 AA) — Sprint 20 Axe E.

Streamlit a des limites structurelles en accessibilité (pas de contrôle fin
du HTML). Ces helpers ajoutent :

* ``plotly_with_alt(fig, alt_text, **kwargs)`` : affiche un chart Plotly
  avec un texte alternatif ``sr-only`` pour les lecteurs d'écran.
* ``folium_with_alt(map_, alt_text, height=500)`` : idem pour les cartes
  Folium (via ``st.components.v1.html``).
* ``data_table_expander(df, label="Données du graphique")`` : ajoute un
  ``st.expander`` avec le DataFrame sous chaque chart (lecteurs d'écran
  peuvent lire la table).

Cf. docs/SPEC_SPRINT_20_UX.md §6.3.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


def plotly_with_alt(fig, alt_text: str = "Graphique interactif — description textuelle à raffiner", **kwargs) -> None:
    """Affiche un chart Plotly avec un texte alternatif sr-only.

    Args:
        fig: Figure Plotly à afficher.
        alt_text: Description textuelle du chart (lue par les lecteurs
            d'écran). Ex: "MAE XGBoost 7.2 km/h, tendance stable".
            Défaut : placeholder à raffiner par le dev pour chaque chart.
        **kwargs: kwargs passés à ``st.plotly_chart`` (ex: use_container_width).
    """
    st.plotly_chart(fig, **kwargs)
    st.markdown(
        f'<p class="sr-only">{alt_text}</p>',
        unsafe_allow_html=True,
    )


def folium_with_alt(map_, alt_text: str, height: int = 500, **kwargs) -> None:
    """Affiche une carte Folium avec un texte alternatif sr-only.

    Args:
        map_: objet folium.Map à rendre.
        alt_text: Description textuelle de la carte.
        height: hauteur en pixels.
        **kwargs: kwargs passés à ``st.components.v1.html``.
    """
    import streamlit.components.v1 as components

    components.html(map_._repr_html_(), height=height, **kwargs)
    st.markdown(
        f'<p class="sr-only">{alt_text}</p>',
        unsafe_allow_html=True,
    )


def data_table_expander(df: pd.DataFrame, label: str = "📋 Données du graphique") -> None:
    """Ajoute un expander avec le DataFrame pour accessibilité.

    Bénéfice double :
    * Accessibilité : les lecteurs d'écran lisent les tables de données
      structurées (vs un chart qui est une image).
    * Transparence : l'usager peut vérifier les chiffres derrière un chart.

    Args:
        df: DataFrame à afficher dans l'expander.
        label: label de l'expander.
    """
    with st.expander(label):
        st.dataframe(df, use_container_width=True, hide_index=True)


def st_folium_with_alt(map_, alt_text: str = "Carte interactive — description textuelle à raffiner", **kwargs):
    """Wrapper st_folium avec texte alternatif sr-only.

    Streamlit-folium a son propre composant qui ne passe pas par
    ``st.components.v1.html``. On wrap l'appel et on ajoute le texte
    sr-only après. Le retour de st_folium (last_clicked, etc.) est
    forwardé tel quel.

    Args:
        map_: objet folium.Map à rendre.
        alt_text: Description textuelle de la carte.
        **kwargs: kwargs passés à ``st_folium`` (width, height, returned_objects).

    Returns:
        Le retour de ``st_folium`` (dict des interactions utilisateur).
    """
    from streamlit_folium import st_folium  # import paresseux (deps lourde)

    result = st_folium(map_, **kwargs)
    st.markdown(
        f'<p class="sr-only">{alt_text}</p>',
        unsafe_allow_html=True,
    )
    return result
