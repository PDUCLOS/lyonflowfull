"""E2E test: Usager Alertes."""
from playwright.sync_api import Page, expect


def test_usager_alertes_page_navigates(page: Page, streamlit_server: str):
    """Naviguer vers /Usager_2_Alertes - page charge (contenu ou erreur DB)."""
    page.goto(f"{streamlit_server}/Usager_2_Alertes")
    page.wait_for_load_state("domcontentloaded")
    # Page charge: titre "Mes alertes" visible
    expect(page.get_by_text("Mes alertes")).to_be_visible(timeout=15000)
