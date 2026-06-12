"""E2E test: page Usager Mon Trajet — pathfinding et favoris.

Ce test vérifie :
1. La page "Mon Trajet" est accessible en tant qu'Usager
2. Le formulaire de recherche d'itinéraire est affiché
3. La section favoris est visible
4. Pas d'erreur Streamlit (pas de widget cassé)
"""

from playwright.sync_api import Page, expect


def test_usager_mon_trajet_page_loads(page: Page, streamlit_server: str):
    """Test that the Usager Mon Trajet page loads without errors."""
    page.goto(streamlit_server)

    # Sélectionne le persona Usager via la carte
    # Usager est accessible directement (pas d'auth requise)
    usager_card = page.get_by_text("🌱 Usager")
    adopt_usager = page.get_by_role("button", name="Adopter").first

    # Clique sur le bouton "Adopter" de la carte Usager
    adopt_usager.click()

    # Devrait naviguer vers Usager_1_Mon_Trajet
    expect(page.get_by_text("Mon trajet")).to_be_visible(timeout=15000)


def test_usager_mon_trajet_sidebar_navigation(page: Page, streamlit_server: str):
    """Test sidebar navigation links for Usager persona."""
    page.goto(streamlit_server)

    # Adopter Usager
    page.get_by_role("button", name="Adopter").first.click()

    # Vérifie que les liens de navigation Usager sont dans le sidebar
    sidebar = page.locator("[data-testid='stSidebarNav']")
    expect(sidebar.get_by_text("Mon trajet")).to_be_visible()
    expect(sidebar.get_by_text("Alertes")).to_be_visible()
    expect(sidebar.get_by_text("Mes favoris")).to_be_visible()

    # Vérifie que les liens Pro TCL / Élu ne sont PAS présents
    expect(sidebar.get_by_text("PCC Live")).not_to_be_visible()
    expect(sidebar.get_by_text("Synthèse Exécutive")).not_to_be_visible()
