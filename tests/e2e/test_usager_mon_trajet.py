"""E2E test: page Usager Mon Trajet — pathfinding et navigation.

Ces tests vérifient :
1. La page "Mon trajet" est accessible en tant qu'Usager
2. Le sidebar affiche les liens Usager (pas Pro TCL / Élu)
"""

from playwright.sync_api import Page, expect


def test_usager_mon_trajet_page_loads(page: Page, streamlit_server: str):
    """Test that the Usager Mon Trajet page loads after adopting Usager persona."""
    page.goto(streamlit_server)

    # Splash screen visible
    expect(page.get_by_text("Bienvenue sur LyonFlowFull")).to_be_visible(timeout=15000)

    # Usager est déjà "✅ Actif" — on clique sur ce bouton disabled pour confirmer
    # ou on peut aussi utiliser le bouton "Changer de profil" puis sélectionner Usager
    # Plus simple : le bouton "✅ Actif" indique le persona actif
    active_btn = page.get_by_role("button", name="✅ Actif")
    assert active_btn.count() > 0, "Le bouton ✅ Actif (Usager) doit être visible"

    # Navigate to Mon Trajet via sidebar link (usager is default)
    sidebar = page.locator("[data-testid='stSidebarNav']")
    sidebar.get_by_text("Mon trajet").click()

    # Devrait être sur Usager_1_Mon_Trajet
    expect(page.get_by_text("Mon trajet")).to_be_visible(timeout=15000)


def test_usager_mon_trajet_sidebar_navigation(page: Page, streamlit_server: str):
    """Test sidebar shows Usager links only, not Pro TCL / Élu."""
    page.goto(streamlit_server)

    # Splash screen visible
    expect(page.get_by_text("Bienvenue sur LyonFlowFull")).to_be_visible(timeout=15000)

    # Navigate to Mon Trajet via sidebar
    sidebar = page.locator("[data-testid='stSidebarNav']")
    sidebar.get_by_text("Mon trajet").click()

    # Vérifie les liens Usager dans le sidebar
    expect(sidebar.get_by_text("Mon trajet")).to_be_visible()
    expect(sidebar.get_by_text("Alertes")).to_be_visible()
    expect(sidebar.get_by_text("Mes favoris")).to_be_visible()

    # Vérifie que les liens Pro TCL / Élu ne sont PAS dans le sidebar
    expect(sidebar.get_by_text("PCC Live")).not_to_be_visible()
    expect(sidebar.get_by_text("Synthèse Exécutive")).not_to_be_visible()
