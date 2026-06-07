"""Locust load test — Streamlit dashboard (sessions websocket).

Lance :
    locust -f kubernetes/loadtest/locustfile.py \
           --host=https://app-dev.lyonflow.fr \
           --users=50 --spawn-rate=2 \
           --run-time=10m --headless
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task


class StreamlitVisitor(HttpUser):
    wait_time = between(2, 8)

    PAGES_USAGER = [
        "/Usager_1_Mon_Trajet",
        "/Usager_2_Alertes",
        "/Usager_3_Favoris",
    ]
    PAGES_PRO = [
        "/Pro_1_PCC_Live",
        "/Pro_2_Heatmap_OTP",
        "/Pro_3_Correlation",
    ]
    PAGES_ELU = [
        "/Elu_1_Synthese",
        "/Elu_2_Bottlenecks",
        "/Elu_3_Avant_Apres",
    ]

    def on_start(self):
        # Premier hit : accueil
        self.client.get("/", name="index")

    @task(5)
    def navigate_usager(self):
        page = random.choice(self.PAGES_USAGER)
        self.client.get(page, name="usager")

    @task(3)
    def navigate_pro(self):
        page = random.choice(self.PAGES_PRO)
        self.client.get(page, name="pro")

    @task(2)
    def navigate_elu(self):
        page = random.choice(self.PAGES_ELU)
        self.client.get(page, name="elu")

    @task(1)
    def health(self):
        self.client.get("/_stcore/health", name="health")
