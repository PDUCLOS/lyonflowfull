# ruff: noqa: RUF001  (typographie française dans les libellés)
"""Mesures reproductibles sans base de données (vitrine, 27/10/2026).

Ce qui est mesuré :
  1. Coût d'entraînement et d'inférence de la VRAIE classe XGBoostSpeedModel
     (3 modèles quantiles P10/P50/P90, 11 features) sur un jeu SYNTHÉTIQUE.
     Les erreurs (MAE…) sur ce jeu ne disent rien de la qualité en production :
     elles ne sont donc pas publiées comme performance du modèle.
  2. Calibrage du PSI maison (src/monitoring/psi.py) sur des décalages connus.
  3. Latence de GET /health de l'API FastAPI (TestClient, sans Postgres).

Usage : python scripts/vitrine/measure.py  →  docs/measures/measures.json
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import statistics
import sys
import tempfile
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["MLFLOW_TRACKING_URI"] = ""  # pas de tracking : mesure locale pure

from src.models.xgboost_speed import FEATURE_COLS, XGBoostSpeedModel  # noqa: E402
from src.monitoring.psi import compute_dataset_drift, compute_psi  # noqa: E402

RNG = np.random.default_rng(42)


def synthetic_traffic(n: int) -> pd.DataFrame:
    """Séries de vitesse plausibles (cycle journalier + bruit), pas 5 min."""
    t = np.arange(n)
    hour = (t * 5 / 60) % 24
    base = 45 - 15 * np.exp(-((hour - 8.5) ** 2) / 2) - 18 * np.exp(-((hour - 18) ** 2) / 3)
    speed = np.clip(base + RNG.normal(0, 4, n), 3, 110)
    s = pd.Series(speed)
    df = pd.DataFrame(
        {
            "speed_kmh": s,
            "lag_1": s.shift(1),
            "lag_2": s.shift(2),
            "lag_3": s.shift(3),
            "rolling_mean_3": s.rolling(3).mean(),
            "sin_hour": np.sin(2 * np.pi * hour / 24),
            "cos_hour": np.cos(2 * np.pi * hour / 24),
            "temperature_2m": 12 + 8 * np.sin(2 * np.pi * hour / 24) + RNG.normal(0, 1, n),
            "precipitation": RNG.exponential(0.2, n) * (RNG.random(n) < 0.15),
            "is_vacances": (t // (288 * 7)) % 5 == 0,
            "is_ferie": RNG.random(n) < 0.01,
            "target_speed": s.shift(-12),
        }
    ).dropna()
    df[["is_vacances", "is_ferie"]] = df[["is_vacances", "is_ferie"]].astype(int)
    return df.reset_index(drop=True)


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(values, q))


def measure_xgboost(n_rows: int = 50_000) -> dict:
    df = synthetic_traffic(n_rows)
    with tempfile.TemporaryDirectory() as tmp:
        model = XGBoostSpeedModel(model_dir=tmp)
        t0 = time.perf_counter()
        model.train_one(horizon_minutes=60, df=df)
        train_s = time.perf_counter() - t0
        pkl_kb = (pathlib.Path(tmp) / "xgb_speed_h60.pkl").stat().st_size / 1024

        row = df.iloc[-1][FEATURE_COLS].to_dict()
        for _ in range(20):  # échauffement
            model.predict("SYNTH", 60, features=row)
        lat = []
        for i in range(1000):
            feats = df.iloc[-1 - (i % 500)][FEATURE_COLS].to_dict()
            t0 = time.perf_counter()
            out = model.predict("SYNTH", 60, features=feats)
            lat.append((time.perf_counter() - t0) * 1000)

        batch = df[FEATURE_COLS].iloc[:10_000]
        p50 = model.models[60]["p50"]
        t0 = time.perf_counter()
        p50.predict(batch)
        batch_ms = (time.perf_counter() - t0) * 1000

    return {
        "dataset": "SYNTHETIQUE (cycle journalier + bruit) — pas de donnée réelle disponible hors VPS",
        "n_rows": len(df),
        "n_features": len(FEATURE_COLS),
        "train_3_quantile_models_s": round(train_s, 2),
        "model_pickle_kb": round(pkl_kb, 1),
        "predict_one_channel_ms": {
            "median": round(statistics.median(lat), 3),
            "p95": round(pct(lat, 95), 3),
            "p99": round(pct(lat, 99), 3),
            "n": len(lat),
            "note": "appel complet XGBoostSpeedModel.predict : DataFrame 1 ligne + 3 modèles P10/P50/P90",
        },
        "batch_10k_rows_p50_ms": round(batch_ms, 2),
        "example_output": out,
    }


def measure_psi() -> dict:
    ref = pd.DataFrame({"x": RNG.normal(40, 10, 20_000)})
    cases = {
        "identique (même loi)": RNG.normal(40, 10, 20_000),
        "décalage +0,25 σ": RNG.normal(42.5, 10, 20_000),
        "décalage +0,5 σ": RNG.normal(45, 10, 20_000),
        "décalage +1 σ": RNG.normal(50, 10, 20_000),
        "variance ×2": RNG.normal(40, 20, 20_000),
    }
    out = {}
    for label, cur in cases.items():
        r = compute_psi(ref["x"], pd.Series(cur))
        out[label] = {"psi": round(r["psi"], 4), "status": r.get("status")}
    cur_df = pd.DataFrame({"x": cases["décalage +1 σ"], "y": RNG.normal(0, 1, 20_000)})
    ref_df = ref.assign(y=RNG.normal(0, 1, 20_000))
    t0 = time.perf_counter()
    ds = compute_dataset_drift(ref_df, cur_df, ["x", "y"])
    out["dataset_drift_2_cols_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    out["dataset_drift_summary"] = ds["_summary"]
    return out


def measure_api() -> dict:
    from fastapi.testclient import TestClient

    from src.api.main import app

    client = TestClient(app)
    lat, codes = [], set()
    for _ in range(200):
        t0 = time.perf_counter()
        r = client.get("/health")
        lat.append((time.perf_counter() - t0) * 1000)
        codes.add(r.status_code)
    return {
        "health_status_codes": sorted(codes),
        "health_body": r.json(),
        "health_ms_median": round(statistics.median(lat), 2),
        "health_ms_p95": round(pct(lat, 95), 2),
        "n": len(lat),
        "note": "TestClient in-process, Postgres absent (db=false attendu)",
    }


if __name__ == "__main__":
    import xgboost

    res = {
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "machine": f"{platform.processor()} · {platform.system()} {platform.release()} · Python {platform.python_version()} · xgboost {xgboost.__version__}",
        "xgboost_speed": measure_xgboost(),
        "psi": measure_psi(),
        "api": measure_api(),
    }
    out = ROOT / "docs" / "measures" / "measures.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
