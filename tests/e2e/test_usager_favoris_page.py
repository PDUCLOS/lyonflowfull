"""E2E test: Usager Favoris."""
from playwright.sync_api import Page, expect


def test_usager_favoris_page_navigates(page: Page, streamlit_server: str):
    """Naviguer vers /Usager_3_Favoris - page charge (contenu ou erreur DB)."""
    page.goto(f"{streamlit_server}/Usager_3_Favoris")
    page.wait_for_load_state("domcontentloaded")
    # Page charge: titre "Mes favoris" visible
    expect(page.get_by_text("Mes favoris")).to_be_visible(timeout=15000)
