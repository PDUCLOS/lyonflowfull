# AUDIT USAGER — Liste des corrections Streamlit

> Audit exhaustif du 2026-06-17. 4 pages Usager + 15 widgets + data layer.
> **15 widgets importent OK, 5 erreurs ruff (import order dans itinerary.py), 0 crash import.**

---

## CRITIQUE — Bug visible en prod

### 1. `render_lieux_velov_map()` — carte Folium jamais rendue

- **Fichier** : `dashboard/components/widgets/usager/lieux_velov_map.py:46-97`
- **Symptôme** : la fonction crée un objet Folium `m` (L85) mais ne l'affiche jamais. La boucle L90-97 écrit des `st.markdown` + `st.caption` en dur (texte brut), puis la fonction se termine sans `st_folium(m, ...)`.
- **Impact** : Usager_1 section "Couverture Vélov des lieux emblématiques" affiche une **liste texte** au lieu de la carte interactive promise.
- **De plus** : `_lieu_popup_html()` (L100) et `_borne_popup_html()` (L128) sont définies mais **jamais appelées** — dead code. `n_paires` et `n_dist_warn` (L87-88) initialisés mais jamais incrémentés ni utilisés.
- **Fix** : compléter la boucle L90-97 pour ajouter markers + polylines au `folium.Map`, puis appeler `st_folium(m, ...)`. Utiliser `_lieu_popup_html()` et `_borne_popup_html()` dans les markers. Supprimer les `st.markdown`/`st.caption` inline qui étaient un placeholder.

### 2. Ligne dupliquée dans `_borne_popup_html()`

- **Fichier** : `dashboard/components/widgets/usager/lieux_velov_map.py:136-141`
- **Texte** : `Relié à <b>{lieu['lieu_name']}</b>` apparaît **deux fois** (L137 et L140). Copier-coller oublié.
- **Fix** : supprimer la ligne L139-141 (doublon).

---

## IMPORTANT — Bugs visibles / dette active

### 3. `_is_demo_mode()` dead code dans `lieux_velov_map.py`

- **Fichier** : `dashboard/components/widgets/usager/lieux_velov_map.py:17, 57-59`
- **Symptôme** : `_is_demo_mode()` retourne toujours `False` (Sprint 8). La branche L57-59 est inatteignable (affiche "Mode démo" et return). Dead code bloquant : si elle n'était pas dead, elle empêcherait la carte de s'afficher.
- **Fix** : supprimer `from src.data.data_loader import _is_demo_mode` et le bloc `if _is_demo_mode(): ...` (L57-59).

### 4. `_is_demo_mode()` dead code dans `pathfinder_multimodal.py` (impact Usager)

- **Fichier** : `src/routing/pathfinder_multimodal.py:31, 276, 539`
- **Symptôme** : `plan_velov_trip()` (L276) et la fonction à L539 ont des branches `if _is_demo_mode()` qui retournent un `VelovItinerary(source="demo")`. Dead code (retourne toujours `False`). Le check `itin.source == "demo"` dans `velov_trip.py:91` est aussi du dead code en conséquence.
- **Fix** : supprimer les 3 occurrences `_is_demo_mode()` dans `pathfinder_multimodal.py` + supprimer le check `itin.source == "demo"` dans `velov_trip.py:91-93`.

### 5. Inline SQL dans `Usager_1_Mon_Trajet.py` — contourne la couche data

- **Fichier** : `dashboard/pages/Usager_1_Mon_Trajet.py:94, 126-137`
- **Symptôme** : importe `execute_query` directement depuis `src.db.connection` et exécute un `SELECT ... FROM referentiel.nearest_velov_stations()` inline. Contourne `db_query.py` + `data_loader.py` + `data_cache.py`.
- **Impact** : pas de cache `@st.cache_data`, pas de gestion d'erreur centralisée (`DashboardDataError`), violation du pattern data layer du projet.
- **Fix** : créer `get_nearest_velov_stations(lat, lon, k=3)` dans `db_query.py`, wrapper dans `data_loader.py`, cache dans `data_cache.py`. Remplacer l'inline SQL dans Usager_1.

### 6. Caption obsolète "Demo session" dans Usager_3_Favoris

- **Fichier** : `dashboard/pages/Usager_3_Favoris.py:38-41`
- **Texte** : `"ℹ️ Demo session — les favoris sont stockés dans la session Streamlit. Backend persistant (table user_favorites) prévu apres release auth."`
- **Impact** : en prod, le mot "Demo" est confusant. La session Streamlit est le stockage réel, pas un fallback démo.
- **Fix** : remplacer par `"ℹ️ Les favoris sont stockés dans la session navigateur. Backend persistant (table user_favorites) prévu Sprint 10+."`

### 7. Bouton "Ajouter un favori" désactivé en permanence

- **Fichier** : `dashboard/pages/Usager_3_Favoris.py:81-82`
- **Texte** : `st.button("➕ Ajouter un trajet favori", disabled=True)` + `st.info("🚧 À venir — Sprint 6+")`
- **Impact** : page inutilisable — on ne peut pas ajouter de favoris. Le Sprint 6 est passé depuis longtemps.
- **Fix** : soit activer le bouton avec un formulaire d'ajout (origin, destination, mode), soit supprimer le bouton mort et la caption associée.

---

## DETTE TECHNIQUE — Nettoyage code

### 8. `_resolve_lieu()` et `_resolve_address()` — même code dupliqué

- **Fichiers** :
  - `dashboard/components/widgets/usager/velov_trip.py:415-456` (`_resolve_lieu`)
  - `dashboard/components/widgets/usager/itinerary.py:29-63` (`_resolve_address`)
- **Symptôme** : deux fonctions quasi-identiques (même SQL, même logic emoji-strip, même `execute_query`). Seule différence : docstring et noms de variables.
- **Fix** : extraire vers `src/data/db_query.py` une seule fonction `resolve_lieu_coords(text: str) -> tuple[float, float] | None`. Les 2 widgets l'importent.

### 9. Docstrings obsolètes mentionnant "mock" / "fallback mock" / "mode démo"

| Fichier | Ligne | Texte obsolète |
|---------|-------|---------------|
| `traffic_widget.py` | 5-6 | "fallback mock si DB down" |
| `traffic_widget.py` | 22 | "Si None, tente DB → fallback mock" |
| `velov_widget.py` | 4 | "(DB Silver ou mock)" |
| `velov_widget.py` | 40 | "Si None, tente DB → fallback mock" |
| `weather_widget.py` | 10 | "Mode démo (LYONFLOW_DEMO_MODE=1) : fallback MOCK_WEATHER autorisé" |
| `weather_widget.py` | 168 | "Si c'est déjà un label FR (mock path)" |
| `search_bar.py` | 4 | "géocodage simulé" / "mock" |
| `Usager_2_Alertes.py` | 31 | "fallback mock auto via data_loader" |

- **Fix** : mettre à jour les docstrings. Sprint 8 = zéro mock. Remplacer par "fail loud via DashboardDataError" ou "DB uniquement".

### 10. Caption "🟡 Données démo (mock — DB non disponible)" dans `traffic_widget.py`

- **Fichier** : `dashboard/components/widgets/usager/traffic_widget.py:37`
- **Symptôme** : si `data_source != "db_gold"`, affiche "Données démo (mock)". Mais il n'y a plus de mock (Sprint 8). En pratique, si la DB est down, `cached_traffic()` lève `DashboardDataError` et le widget ne s'affiche pas.
- **Impact** : branche L36-37 potentiellement inatteignable, ou trompeuse si atteinte.
- **Fix** : supprimer la branche `else` L37, ou remplacer par `"🟡 Source inconnue — données potentiellement stales"`.

### 11. `velov_trip.py:91-93` — check `itin.source == "demo"` dead code

- **Fichier** : `dashboard/components/widgets/usager/velov_trip.py:91-93`
- **Symptôme** : `plan_velov_trip()` ne retourne plus `source="demo"` en prod (`_is_demo_mode()` = `False`). Le message "Mode démo" est inatteignable.
- **Fix** : supprimer le bloc L91-93. (Lié au point 4.)

### 12. `Usager_4_Files.py:183-287` — 100 lignes pydeck dupliquant `gnn_map.py`

- **Fichier** : `dashboard/pages/Usager_4_Files.py:183-287`
- **Symptôme** : "Super carte trafic Lyon" = copie inline de la logique `_load_merged` + `_render_pydeck` de `gnn_map.py`, avec son propre `_speed_to_rgba`, sa propre jointure, son propre tooltip. Si `gnn_map.py` évolue, cette copie diverge.
- **Impact** : ~100 lignes de code dupliqué. Maintenance double.
- **Fix** : remplacer par `render_traffic_map_compact(key_suffix="files")` (de `gnn_map.py`). 3 lignes au lieu de 100.

### 13. `itinerary.py` — import E402 + I001 (ruff)

- **Fichier** : `dashboard/components/widgets/usager/itinerary.py:19-26, 102`
- **Symptôme** : 5 erreurs ruff — imports après `logger = logging.getLogger(__name__)` (E402) + import block non trié (I001).
- **Fix** : déplacer `logger = ...` après les imports. `ruff check --fix` corrige le I001.

### 14. `weather_widget.py:160` — `Any` non importé

- **Fichier** : `dashboard/components/widgets/usager/weather_widget.py:160`
- **Symptôme** : `def _wmo_to_label(code: Any)` utilise `Any` mais ne l'importe pas de `typing`. Pas de crash runtime grâce à `from __future__ import annotations`, mais erreur mypy/ruff.
- **Fix** : ajouter `from typing import Any` ou changer en `code: object`.

### 15. `weather_widget.py:109` — `_weather_icon()` quasi-redondante

- **Fichier** : `dashboard/components/widgets/usager/weather_widget.py:109-119`
- **Symptôme** : `_weather_icon()` mappe 6 labels FR → emoji. `_wmo_to_label()` (L160) fait la même chose plus complètement via `_WMO_CODE_MAP`. `_weather_icon` n'est appelée que par `_wmo_to_label` elle-même (L170).
- **Fix** : supprimer `_weather_icon()` et faire le lookup inline dans `_wmo_to_label` ou simplement retourner l'emoji du `_WMO_CODE_MAP`.

### 16. `force_mock=False` passé partout (7 occurrences)

- **Fichiers** : `search_bar.py:32`, `weather_widget.py:30`, `traffic_widget.py:25`, `velov_widget.py:24,44`, `velov_map.py:57,58`
- **Symptôme** : `cached_*()` prennent un param `force_mock` qui n'a plus d'effet (Sprint 8 zéro mock). `force_mock=False` est le défaut.
- **Impact** : bruit de code, confusion lecteur.
- **Fix** : supprimer le paramètre `force_mock` des appels (laisser le défaut). Idéalement, supprimer le param des fonctions `data_cache.py` elles-mêmes (scope plus large, hors Usager).

---

## RÉSUMÉ PRIORISATION

| # | Sévérité | Effort | Description |
|---|----------|--------|-------------|
| 1 | 🔴 CRITIQUE | 30 min | Compléter `render_lieux_velov_map()` — carte Folium jamais rendue |
| 2 | 🔴 CRITIQUE | 1 min | Supprimer ligne dupliquée popup `_borne_popup_html` |
| 3 | 🟠 IMPORTANT | 2 min | Supprimer `_is_demo_mode()` dans `lieux_velov_map.py` |
| 4 | 🟠 IMPORTANT | 5 min | Supprimer `_is_demo_mode()` dans `pathfinder_multimodal.py` (3×) + `velov_trip.py` |
| 5 | 🟠 IMPORTANT | 20 min | Extraire inline SQL de Usager_1 vers `db_query.py` |
| 6 | 🟠 IMPORTANT | 1 min | Fix caption "Demo session" Usager_3 |
| 7 | 🟠 IMPORTANT | 15 min | Activer ou supprimer bouton "Ajouter favori" Usager_3 |
| 8 | 🟡 DETTE | 15 min | Extraire `_resolve_lieu` / `_resolve_address` en 1 seule fn `db_query.py` |
| 9 | 🟡 DETTE | 10 min | Nettoyer docstrings obsolètes "mock/démo" (8 fichiers) |
| 10 | 🟡 DETTE | 2 min | Fix caption "Données démo" `traffic_widget.py:37` |
| 11 | 🟡 DETTE | 2 min | Supprimer check `itin.source == "demo"` `velov_trip.py` |
| 12 | 🟡 DETTE | 10 min | Remplacer pydeck inline Usager_4 par `render_traffic_map_compact()` |
| 13 | 🟡 DETTE | 2 min | Fix ruff E402/I001 dans `itinerary.py` |
| 14 | ⚪ COSM | 1 min | Importer `Any` dans `weather_widget.py` |
| 15 | ⚪ COSM | 2 min | Supprimer `_weather_icon()` redondante |
| 16 | ⚪ COSM | 5 min | Supprimer `force_mock=False` (7 appels) |

**Total estimé : ~120 min**

---

## CE QUI MARCHE BIEN (pas toucher)

- Tous les imports OK (15 widgets, 4 pages)
- `__init__.py` exports alignés sur tous les fichiers
- `velov_trip.py` : trajet Vélov + marche + alternatives + maillage complet
- `velov_map.py` : carte pydeck stations + prédictions H+30/H+1h fonctionnelle
- `velov_widget.py` : dispo stations proches + prédictions H+1h
- `itinerary.py` : carte Folium itinéraire voiture + snap-to-roads + segments
- `alert_card.py` / `alert_timeline.py` / `alert_settings.py` : fonctionnels
- `recommendation_card.py` / `alternative_card.py` / `why_explainer.py` : fonctionnels
- `favorite_list.py` : rendu liste correct (le problème est l'ajout, pas l'affichage)
- `weather_widget.py` : WMO code mapping complet, rendu météo + conseil vélo
- `search_bar.py` : branché DB via `cached_lyon_addresses_with_coords`
- Ruff : 0 erreur sauf `itinerary.py` (5 E402/I001)
