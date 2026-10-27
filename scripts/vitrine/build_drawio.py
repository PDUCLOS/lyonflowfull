# ruff: noqa: RUF001  (typographie française dans les libellés)
"""Génère docs/architecture.drawio (3 pages) à partir de positions explicites.

Les flèches sont orthogonales avec points de sortie / d'entrée imposés, pour
un rendu propre ; chaque page est ensuite exportée en PNG par draw.io CLI
(cf. scripts/vitrine/export_drawio.ps1) et contrôlée visuellement.
"""

from __future__ import annotations

import pathlib
from xml.sax.saxutils import escape

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "architecture.drawio"

PAL = {
    "source": ("#dae8fc", "#6c8ebf"),
    "ingest": ("#fff2cc", "#d6b656"),
    "bronze": ("#f8cecc", "#b85450"),
    "silver": ("#f5f5f5", "#666666"),
    "gold": ("#ffe6cc", "#d79b00"),
    "ml": ("#e1d5e7", "#9673a6"),
    "ops": ("#d5e8d4", "#82b366"),
    "serve": ("#dae8fc", "#3a6ea5"),
    "todo": ("#ffffff", "#999999"),
    "k8s": ("#e6f0ff", "#326ce5"),
}


class Page:
    def __init__(self, name: str, width: int, height: int):
        self.name, self.width, self.height = name, width, height
        self.cells: list[str] = []
        self.n = 0

    def _id(self) -> str:
        self.n += 1
        return f"c{self.n}"

    def box(self, x, y, w, h, label, kind="source", *, dashed=False, bold=False, font=13, rounded=True) -> str:
        cid = self._id()
        fill, stroke = PAL[kind]
        style = (
            f"rounded={int(rounded)};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
            f"fontSize={font};arcSize=10;spacing=4;"
            + ("dashed=1;fontColor=#666666;" if dashed else "")
            + ("fontStyle=1;" if bold else "")
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        return cid

    def group(self, x, y, w, h, label, kind="silver") -> str:
        cid = self._id()
        fill, stroke = PAL[kind]
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};opacity=45;"
            "verticalAlign=top;align=left;spacingLeft=10;spacingTop=4;fontSize=14;fontStyle=1;arcSize=4;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        return cid

    def text(self, x, y, w, h, label, *, font=12, color="#333333", align="left", bold=False) -> str:
        cid = self._id()
        style = f"text;html=1;whiteSpace=wrap;align={align};verticalAlign=middle;fontSize={font};fontColor={color};" + (
            "fontStyle=1;" if bold else ""
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        return cid

    def edge(self, src, dst, label="", *, exit=(1, 0.5), entry=(0, 0.5), dashed=False, color="#555555", points=()):
        cid = self._id()
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeWidth=1.6;"
            f"strokeColor={color};fontSize=11;labelBackgroundColor=#ffffff;"
            f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
            + ("dashed=1;" if dashed else "")
        )
        pts = "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in points)
        geom = f'<mxGeometry relative="1" as="geometry">{'<Array as="points">' + pts + "</Array>" if pts else ""}</mxGeometry>'
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label)}" style="{style}" edge="1" parent="1" source="{src}" target="{dst}">'
            f"{geom}</mxCell>"
        )
        return cid

    def xml(self, idx: int) -> str:
        body = "".join(self.cells)
        return (
            f'<diagram id="p{idx}" name="{escape(self.name)}"><mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" '
            f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.width}" '
            f'pageHeight="{self.height}" background="#ffffff" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f"{body}</root></mxGraphModel></diagram>"
        )


def page_overview() -> Page:
    p = Page("1 - Vue d'ensemble", 1700, 820)
    p.text(
        30,
        15,
        1640,
        40,
        "LyonFlow — du flux open data à la décision (architecture Medallion sur PostgreSQL)",
        font=20,
        bold=True,
    )
    p.text(
        30,
        52,
        1640,
        24,
        "Collecte 5 min → 6 h · Bronze immuable · Silver nettoyé · Gold features + vues métier · XGBoost H+1h · 3 personas",
        font=13,
        color="#555555",
    )

    p.group(20, 90, 230, 520, "1. Sources (9, sans clé)", "source")
    srcs = [
        "Boucles trafic\nGrand Lyon (WFS)",
        "TCL SIRI Lite\n(positions bus)",
        "Vélo'v GBFS\n(~458 stations)",
        "Open-Meteo\nmétéo + air",
        "TomTom · chantiers\nvigilance · calendriers",
    ]
    sids = [p.box(40, 130 + i * 92, 190, 70, s.replace("\n", "<br>"), "source") for i, s in enumerate(srcs)]

    p.group(280, 90, 220, 520, "2. Ingestion (Airflow)", "ingest")
    a1 = p.box(300, 180, 180, 90, "<b>collect_bronze</b><br>*/5 min · 6 sources temps réel", "ingest")
    a2 = p.box(
        300, 400, 180, 110, "<b>collect_tomtom</b> */15<br><b>vigilance</b> 6 h<br><b>calendriers</b> mensuel", "ingest"
    )

    p.group(530, 90, 560, 520, "3. Medallion — PostgreSQL 16 + PostGIS + pgRouting", "silver")
    b = p.box(550, 280, 150, 110, "<b>Bronze</b><br>JSONB brut<br>immuable", "bronze")
    s = p.box(735, 280, 150, 110, "<b>Silver</b><br>dédup DISTINCT ON<br>parsing SIRI, 4326/2154", "silver")
    g = p.box(920, 280, 150, 110, "<b>Gold</b><br>features ML<br>vues matérialisées", "gold")
    osm = p.box(920, 470, 150, 80, "<b>osm.*</b><br>~101 k arêtes", "gold")
    p.text(
        550,
        130,
        520,
        120,
        "transform_bronze_to_silver (2-57/5)<br>transform_silver_to_gold (:05 :20 :35 :50)<br>refresh_heavy_mv (:15 :45)<br>purge_bronze 7 j · silver_archive_to_minio",
        font=12,
    )

    p.group(1120, 90, 260, 520, "4. Modèles", "ml")
    m1 = p.box(1140, 140, 220, 80, "<b>XGBoost vitesse H+1h</b><br>train 03:38 · inférence */15", "ml")
    m2 = p.box(1140, 250, 220, 80, "<b>XGBoost Vélo'v H+1h</b><br>retrain :50 · inférence 15 min", "ml")
    m3 = p.box(1140, 470, 220, 80, "<b>pgRouting</b><br>pgr_dijkstra voiture", "ml")
    mf = p.box(1140, 360, 220, 80, "<b>MLflow 2.12</b> registry<br>+ drift PSI / Evidently", "ops")

    p.group(1410, 90, 270, 520, "5. Restitution", "serve")
    api = p.box(1430, 180, 230, 90, "<b>FastAPI</b><br>/predict · /recommend<br>X-API-Key", "serve")
    st = p.box(1430, 360, 230, 110, "<b>Streamlit</b><br>18 pages · 59 widgets<br>Usager · Pro TCL · Élu", "serve")

    for i, sid in enumerate(sids):
        p.edge(sid, a1 if i < 3 else a2)
    p.edge(a1, b, entry=(0, 0.3))
    p.edge(a2, b, entry=(0, 0.75))
    p.edge(b, s)
    p.edge(s, g)
    p.edge(g, m1, "features", entry=(0, 0.5), exit=(0.5, 0))
    p.edge(g, m2, exit=(1, 0.25))
    p.edge(osm, m3)
    p.edge(
        m1, mf, "log", exit=(1, 0.5), entry=(1, 0.5), dashed=True, color="#82b366", points=((1375, 180), (1375, 400))
    )
    p.edge(m1, api, exit=(1, 0.3), entry=(0, 0.3))
    p.edge(m3, st, exit=(1, 0.5), entry=(0, 0.75))
    p.edge(api, st, exit=(0.5, 1), entry=(0.5, 0))

    p.box(
        20,
        640,
        1660,
        60,
        "<b>Socle</b> : Docker Compose sur un VPS unique · Nginx seul point exposé (TLS) · GitHub Actions (ruff · mypy · bandit · pytest) · make deploy-vps / rollback-vps · Prometheus + Grafana (compose monitoring)",
        "todo",
        font=13,
    )
    p.text(
        20,
        715,
        1660,
        60,
        "Inventaire mesuré : 28 appels DAG(...) dans dags/ dont 1 legacy → 27 DAGs, 1 marqué PAUSED (retrain_xgboost_speed). Planifications lues dans le code (scripts/vitrine/count_dags.py).",
        font=12,
        color="#555555",
    )
    return p


def page_mlops() -> Page:
    p = Page("2 - Cycle MLOps", 1600, 760)
    p.text(
        30, 15, 1540, 40, "Cycle de vie du modèle vitesse H+1h — planifications réelles des DAGs", font=20, bold=True
    )

    t1 = p.box(40, 120, 220, 90, "<b>build_xgb_training_set</b><br>02:30 · jeu d'entraînement Gold", "ingest")
    t2 = p.box(320, 120, 220, 90, "<b>dag_daily_speed_train</b><br>03:38 · split 80/20 · pool ml_training", "ml")
    reg = p.box(600, 120, 220, 90, "<b>MLflow registry</b><br>log_model → stage Production<br>chargé par l'inférence", "ops")
    inf = p.box(880, 120, 220, 90, "<b>dag_inference_xgboost</b><br>*/15 min → gold.predictions", "ml")
    app = p.box(1160, 120, 220, 90, "<b>FastAPI / Streamlit</b><br>prévision servie aux 3 personas", "serve")

    cmp = p.box(880, 330, 220, 90, "<b>refresh_xgb_vs_tomtom</b><br>:05 :35 · écart à la vérité TomTom", "gold")
    drift = p.box(
        600,
        330,
        220,
        90,
        "<b>daily_drift_report</b><br>05:30 · PSI erreurs XGB vs TomTom<br>(Evidently en option)",
        "ops",
    )
    p.box(320, 330, 220, 90, "<b>dag_critical_pipeline_health</b><br>:02 :17 :32 :47 · fraîcheur Gold", "ops")
    dq = p.box(40, 330, 220, 90, "<b>data_quality_daily</b><br>04:15 · 6 contrôles qualité", "ops")

    p.edge(t1, t2)
    p.edge(t2, reg)
    p.edge(reg, inf)
    p.edge(inf, app)
    p.edge(inf, cmp, exit=(0.5, 1), entry=(0.5, 0))
    p.edge(cmp, drift, exit=(0, 0.5), entry=(1, 0.5))
    p.edge(
        drift,
        app,
        "gold.model_drift_reports → badge dérive",
        exit=(0.5, 1),
        entry=(1, 0.5),
        dashed=True,
        color="#b85450",
        points=((710, 470), (1410, 470), (1410, 165)),
    )

    p.group(40, 520, 1340, 200, "Vélo'v H+1h (même chaîne, cadence horaire)", "ml")
    v1 = p.box(70, 570, 260, 80, "<b>retrain_xgboost_velov</b><br>chaque heure à :50", "ml")
    v2 = p.box(420, 570, 260, 80, "<b>MLflow</b> xgb_velov_h60", "ops")
    v3 = p.box(770, 570, 260, 80, "<b>dag_inference_velov</b><br>:04 :19 :34 :49", "ml")
    v4 = p.box(1100, 570, 250, 80, "<b>Alerte disponibilité</b><br>persona Usager", "serve")
    p.edge(v1, v2)
    p.edge(v2, v3)
    p.edge(v3, v4)
    p.text(
        1430,
        120,
        160,
        300,
        "<b>Seuils PSI</b> (src/monitoring/psi.py)<br>&lt; 0,1 stable<br>0,1–0,2 modéré<br>&gt; 0,2 dérive significative<br><br>"
        "Le réentraînement est <b>planifié</b>, pas déclenché par la dérive : la dérive est affichée aux personas.<br><br>"
        "retrain_xgboost_speed horaire : <b>en pause</b> depuis le 01/07/2026 (redondant avec l'entraînement quotidien).",
        font=12,
    )
    return p


def page_k8s() -> Page:
    p = Page("3 - Cible Kubernetes", 1600, 820)
    p.text(
        30,
        15,
        1540,
        40,
        "Cible Kubernetes (deploy/k8s) — rendue et validée par kubectl kustomize, non déployée",
        font=20,
        bold=True,
    )

    usr = p.box(40, 330, 150, 80, "Utilisateurs<br>(3 personas)", "source")
    ing = p.box(250, 330, 170, 80, "<b>ingress-nginx</b><br>+ cert-manager TLS", "k8s")
    p.group(470, 80, 860, 600, "namespace lyonflow (NetworkPolicy default-deny)", "k8s")
    api = p.box(500, 160, 220, 90, "<b>Deployment fastapi</b><br>HPA 2→10 (prod 3→15)<br>PDB minAvailable 1", "serve")
    st = p.box(500, 470, 220, 90, "<b>Deployment streamlit</b><br>HPA · PDB", "serve")
    pg = p.box(
        820,
        300,
        220,
        110,
        "<b>StatefulSet postgres</b><br>pgrouting 16-3.5-3.7.3<br>PVC 10 Gi dev / 100 Gi prod",
        "gold",
    )
    mlf = p.box(820, 130, 220, 90, "<b>Deployment mlflow</b> 2.12.1<br>PVC artefacts 20 Gi", "ops")
    bk = p.box(820, 500, 220, 80, "<b>CronJob postgres-backup</b><br>pg_dump 02:00 · 7 copies", "ops")
    af = p.box(1100, 300, 200, 110, "<b>Airflow</b> (Helm)<br>KubernetesExecutor<br>git-sync dags/ (main)", "ingest")
    p.box(1100, 130, 200, 90, "<b>Secret lyonflow-secrets</b><br>dev : généré factice<br>prod : SealedSecret", "todo")
    p.box(1100, 500, 200, 80, "<b>Component monitoring</b><br>ServiceMonitor ×3 · règles", "ops")

    p.edge(usr, ing)
    p.edge(ing, api, exit=(1, 0.3), entry=(0, 0.5))
    p.edge(ing, st, exit=(1, 0.7), entry=(0, 0.5))
    p.edge(api, pg, exit=(1, 0.7), entry=(0, 0.3))
    p.edge(st, pg, exit=(1, 0.3), entry=(0, 0.7))
    p.edge(api, mlf, exit=(1, 0.3), entry=(0, 0.5))
    p.edge(af, pg, exit=(0, 0.5), entry=(1, 0.5))
    p.edge(bk, pg, exit=(0.5, 0), entry=(0.5, 1))

    p.group(40, 700, 1290, 100, "Reste à faire (non couvert par les manifestes)", "todo")
    p.text(
        60,
        735,
        1260,
        60,
        "Publier l'image ghcr.io/pduclos/lyonflowfull-app · manifeste MinIO (ou S3 managé) · ClusterIssuer cert-manager · "
        "valider les 27 DAGs sous KubernetesExecutor · migration du dump Postgres du VPS · kubectl apply --dry-run=server sur un cluster",
        font=12,
    )
    p.text(
        1350,
        80,
        230,
        320,
        "<b>Validation mesurée</b><br>kubectl kustomize<br>overlays/dev : 1 759 lignes<br>overlays/prod : 1 972 lignes<br><br>"
        "<b>Non fait</b> : aucun apply, aucun pod démarré (pas de cluster sur la machine de test).",
        font=12,
    )
    return p


def main() -> None:
    pages = [page_overview(), page_mlops(), page_k8s()]
    xml = (
        '<mxfile host="build_drawio.py" version="24.0.0">'
        + "".join(pg.xml(i) for i, pg in enumerate(pages))
        + "</mxfile>"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(xml, encoding="utf-8")
    print(f"{OUT} : {len(pages)} pages")


if __name__ == "__main__":
    main()
