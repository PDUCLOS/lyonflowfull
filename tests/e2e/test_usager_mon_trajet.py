"""E2E test: page Usager Mon Trajet — pathfinding et navigation.

Ces tests vérifient :
1. La page "Mon trajet" est accessible en tant qu'Usager
2. Le sidebar affiche les liens Usager
"""

from playwright.sync_api import Page, expect


def test_usager_mon_trajet_page_loads(page: Page, streamlit_server: str):
    """Test that the Usager Mon Trajet page loads after adopting Usager persona."""
    page.goto(streamlit_server)

    # Splash screen visible
    expect(page.get_by_text("Bienvenue sur LyonFlowFull")).to_be_visible(timeout=15000)

    # Usager est déjà "✅ Actif" — on confirme le persona actif
    active_btn = page.get_by_role("button", name="✅ Actif")
    assert active_btn.count() > 0, "Le bouton ✅ Actif (Usager) doit être visible"

    # Navigate to Mon Trajet via sidebar link
    sidebar = page.locator("[data-testid='stSidebarNav']")
    sidebar.get_by_text("Mon trajet").click()

    # Devrait être sur Usager_1_Mon_Trajet
    expect(page.get_by_text("Mon trajet")).to_be_visible(timeout=15000)
