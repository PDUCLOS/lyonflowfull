# ADR-0002 : 3 personas en 1 dashboard

## Statut
Accepté (2026-06-06)

## Contexte
Trois audiences cibles (usager, Pro TCL, élu) avec des besoins très
différents. Trois options :
1. 3 apps séparées (FastAPI × 3)
2. **1 dashboard avec sélecteur de persona**
3. Mode responsive (1 seule UI)

## Décision
1 dashboard Streamlit unique avec :
- `config/personas.yaml` comme source de vérité
- `src/persona/manager.py` pour le state management
- Sélecteur dans la sidebar
- 3-5 pages par persona, navigation filtrée

## Conséquences
- 1 codebase à maintenir
- Authentification centralisée
- Modèles ML partagés
- Tests partagés
- Plus complexe qu'1 app simple
- Performance : 1 app pour 3 audiences (mitigé par cacher)

## Notes
- Auth par mot de passe (env var) — pas de SSO à ce stade
- Sprint 6+ : SSO OAuth pour Pro TCL et Élu
