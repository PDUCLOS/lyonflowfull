"""Sprint 8 (2026-06-12) — Fixtures de test.

Contient les données mock (statiques ou générées) utilisées par les
tests. Avant : ces données étaient dans ``src/data/mock/``, ce qui
laissait penser que le code de prod les utilisait. C'est une dette
de nomenclature qui a été corrigée : ``src/data/mock/`` est
supprimé, les mocks sont maintenant dans ``tests/fixtures/mock_data/``.

Note : pour les tests qui ont vraiment besoin d'une DB, on utilise
la fixture ``mock_db`` du conftest centralisé (qui monkeypatch
``src.db.connection.execute_query``). Pour les tests widgets
anciens, on garde les constantes mock ici pour la compatibilité.
"""
