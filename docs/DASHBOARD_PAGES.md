# Logique et Architecture des Pages du Dashboard

Ce document centralise la documentation de toutes les pages de l'application Streamlit `LyonFlowFull`. Le projet repose sur une approche **Multi-Persona** : une même application sert 3 types d'utilisateurs avec des interfaces et des logiques complètement différentes.

La navigation est gérée dynamiquement par `dashboard/components/navigation.py` qui lit le fichier `config/personas.yaml` pour restreindre l'accès et l'affichage.

---

## 🚦 Pages Communes (Accessibles à tous)

### `Accueil.py`
**Logique :** Point d'entrée principal (Onboarding).
- Affiche les 3 cartes des personas (Usager, Pro TCL, Élu).
- Agit comme un Splash Screen. Si un utilisateur sélectionne un profil protégé, il demande un mot de passe via `src/persona/auth.py`.
- Affiche un footer avec des statistiques globales de la Métropole en live.

### `9_RGPD_Conformite.py`
**Logique :** Page de transparence et d'audit RGPD.
- Affiche la politique de traitement des données.
- Permet de voir l'état des consentements (anonymisés) et les audits de purge depuis la base PostgreSQL (`cached_rgpd_audit`).

### `A_Propos.py`
**Logique :** Présentation du projet LyonFlowFull (architecture, modèles, MLOps).

---

## 🧭 Persona "Usager" (Grand public)
Interface orientée "B2C", gratuite et sans mot de passe, axée sur le confort de voyage.

### `Usager_1_Mon_Trajet.py`
**Logique :** Moteur de recherche d'itinéraire multimodal (Transport en commun, Vélo, Marche, Voiture).
- Contient une barre de recherche élégante avec auto-complétion sur les adresses lyonnaises.
- Affiche les recommandations de trajet calculées (ou mockées si l'API de routing n'est pas finalisée).
- Fournit le contexte en temps réel : Météo (`silver.meteo_hourly`), disponibilité Vélo'v (`bronze.velov`), et une carte de trafic compacte basée sur le modèle GNN.

### `Usager_2_Alertes.py`
**Logique :** Suivi des perturbations en temps réel.
- Connecté à `silver.chantiers_actifs` pour lister les travaux en cours sur la voirie.
- Affiche une timeline des alertes et permet à l'usager de régler ses préférences d'alerte.

### `Usager_3_Favoris.py`
**Logique :** Gestion des trajets récurrents.
- Permet à l'utilisateur de sauvegarder ses adresses domicile/travail.
- Affiche les prévisions pour les trajets favoris en un clin d'œil.

### `Usager_4_Files.py`
**Logique :** (Optionnelle) Interface permettant l'upload ou le download de pièces justificatives ou de configurations (File Manager basique).

---

## 🔧 Persona "Pro TCL" (Exploitant réseau)
Interface "B2B" protégée par mot de passe, axée sur la gestion du réseau, la corrélation trafic/bus et le MLOps.

### `Pro_1_PCC_Live.py`
**Logique :** Poste de Commande Centralisé (Live 4 quadrants).
- Affiche une vue macro du réseau en temps réel.
- Combine une carte des bus en temps réel, un fil d'actualité des alertes, et des KPIs de ponctualité sur les lignes majeures.

### `Pro_2_Heatmap_OTP.py`
**Logique :** Suivi de la ponctualité.
- Affiche une carte de chaleur (Heatmap) de l'Offre Théorique vs Pratique (OTP).
- Permet de repérer visuellement les zones où les bus prennent systématiquement du retard.

### `Pro_3_Correlation.py`
**Logique :** L'Argumentaire Technique (USP) du projet.
- Croise les données de ralentissement routier (modèles XGBoost/GNN) avec les retards de bus.
- Affiche une matrice de corrélation pour prouver que le trafic routier est la cause des retards TCL sur certains segments.

### `Pro_4_Simulateur.py`
**Logique :** Outil de planification à court terme.
- Permet à l'exploitant de simuler des modifications de fréquence de bus.
- Calcule l'impact théorique sur le taux de charge et l'attente voyageur (A/B testing Avant/Après).

### `Pro_5_Export.py`
**Logique :** Génération de rapports métiers (SAEIV).
- Exporte les données de performance du réseau aux formats PDF/CSV pour les revues de direction.

### `Pro_6_Pipeline_Mgmt.py`
**Logique :** Interface Data Engineering.
- Surcouche au-dessus d'Airflow. Permet de vérifier la "fraîcheur" des données (bronze/silver/gold) et de relancer des pipelines d'ingestion directement depuis Streamlit.

### `Pro_7_Model_Monitoring.py`
**Logique :** Interface MLOps.
- Surcouche au-dessus de MLflow. Permet de suivre les performances des modèles de prédiction (XGBoost / STGCN).
- Affiche les graphes de Model Drift et permet l'activation/désactivation de la carte GNN.

---

## 🏛️ Persona "Élu" (Décideur politique)
Interface stratégique, protégée par mot de passe, axée sur l'aide à la décision pour de gros investissements (aménagements urbains).

### `Elu_1_Synthese.py`
**Logique :** Tableau de bord exécutif (Executive Summary).
- Fournit des KPIs macro-économiques et environnementaux sur 12 mois.

### `Elu_2_Bottlenecks.py`
**Logique :** Identification des points noirs.
- Affiche un classement des pires goulets d'étranglement de la Métropole (là où les bus perdent le plus de temps et coûtent de l'argent à la collectivité).

### `Elu_3_Avant_Apres.py`
**Logique :** Évaluation des travaux passés.
- Permet de sélectionner un aménagement (ex: création d'une voie bus) et de comparer les statistiques de trafic et de retard "Avant" et "Après" les travaux pour mesurer le succès de l'investissement.

### `Elu_4_Simulateur.py`
**Logique :** Planification d'investissements futurs.
- Outil de simulation "Et si ?". L'élu peut dessiner/sélectionner un couloir de bus virtuel sur une carte.
- Calcule un retour sur investissement (ROI) estimé : Coût des travaux vs. Économies d'exploitation générées par le gain de vitesse des bus.

### `Elu_5_Rapport.py`
**Logique :** Outil de communication politique.
- Génère automatiquement un diaporama (slides) ou un rapport PDF prêt à être présenté en Conseil Municipal ou Métropolitain pour justifier des décisions d'urbanisme.
