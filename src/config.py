"""LyonFlowFull — Configuration centralisée.

Charge les variables d'environnement via Pydantic Settings. Validation au
boot : si une variable requise est manquante, l'app ne démarre pas.

Tous les chemins (DB, MinIO, modèles) sont dérivés des env vars.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Workspace root (used for resolving relative paths in tests)
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class DatabaseSettings(BaseSettings):
    """Connexion PostgreSQL."""

    host: str = Field(default="localhost", alias="POSTGRES_HOST")
    port: int = Field(default=5432, alias="POSTGRES_PORT")
    db: str = Field(default="lyonflow", alias="POSTGRES_DB")
    user: str = Field(default="lyonflow", alias="POSTGRES_USER")
    # Default "" pour permettre l'import en dev/test.
    # validate_settings() refuse un password vide en production.
    password: str = Field(default="dev-password-not-for-prod", alias="POSTGRES_PASSWORD")

    # Sous-DBs (Airflow, MLflow utilisent la même instance)
    airflow_db: str = "airflow"
    mlflow_db: str = "mlflow"

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def airflow_url(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.airflow_db}"

    @property
    def mlflow_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.mlflow_db}"


class MinioSettings(BaseSettings):
    """MinIO S3-compatible storage (optionnel — Google Drive est préféré)."""

    enabled: bool = Field(default=False, alias="MINIO_ENABLED")
    endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    root_user: str = Field(default="minio", alias="MINIO_ROOT_USER")
    root_password: str = Field(default="", alias="MINIO_ROOT_PASSWORD")
    bucket_bronze: str = "lyonflow-bronze"
    bucket_gold: str = "lyonflow-gold"

    @property
    def url(self) -> str:
        return f"http://{self.endpoint}"


class GoogleDriveSettings(BaseSettings):
    """Google Drive API pour artifacts + file sharing.

    Setup :
    1. Créer un projet Google Cloud
    2. Activer l'API Google Drive
    3. Créer un OAuth 2.0 Client ID (Desktop app)
    4. Télécharger credentials.json → GDRIVE_CREDENTIALS_PATH
    5. Premier lancement : flow OAuth → token.json
    6. Créer un dossier partagé (ou utiliser My Drive)
    7. Récupérer le folder ID → GDRIVE_FOLDER_ID

    Alternative MLflow : filesystem + rclone sync vers Drive
    """

    enabled: bool = Field(default=True, alias="GDRIVE_ENABLED")
    credentials_path: str = Field(
        default="/app/secrets/gdrive_credentials.json",
        alias="GDRIVE_CREDENTIALS_PATH",
    )
    token_path: str = Field(
        default="/app/secrets/gdrive_token.json",
        alias="GDRIVE_TOKEN_PATH",
    )
    folder_id_artifacts: str = Field(default="", alias="GDRIVE_FOLDER_ID_ARTIFACTS")
    folder_id_user_files: str = Field(default="", alias="GDRIVE_FOLDER_ID_USER_FILES")
    folder_id_bronze_backup: str = Field(default="", alias="GDRIVE_FOLDER_ID_BRONZE")


class RedisSettings(BaseSettings):
    """Redis (cache + Celery broker)."""

    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")


class MLflowSettings(BaseSettings):
    """MLflow tracking."""

    tracking_uri: str = Field(default="http://localhost:5000", alias="MLFLOW_TRACKING_URI")
    experiment_name: str = "lyonflow-traffic"


class APISettings(BaseSettings):
    """FastAPI."""

    key: str = Field(default="", alias="LYONFLOW_API_KEY")
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:8501", "http://localhost"]


class AirflowSettings(BaseSettings):
    """Airflow."""

    admin_username: str = Field(default="admin", alias="AIRFLOW_ADMIN_USERNAME")
    admin_password: str = Field(default="", alias="AIRFLOW_ADMIN_PASSWORD")
    secret_key: str = Field(default="", alias="AIRFLOW_SECRET_KEY")
    fernet_key: str = Field(default="", alias="AIRFLOW_FERNET_KEY")


class MLSettings(BaseSettings):
    """Hyperparamètres ML."""

    seq_len: int = Field(default=120, alias="SEQ_LEN")
    horizons: list[int] = Field(default=[6, 12, 36], alias="HORIZONS")
    hidden_channels: int = Field(default=128, alias="HIDDEN_CHANNELS")
    weight_jam: float = Field(default=15.0, alias="WEIGHT_JAM")
    weight_slow: float = Field(default=5.0, alias="WEIGHT_SLOW")
    default_speed_kmh: float = Field(default=30.0, alias="LYON_DEFAULT_SPEED")
    # ---- Sprint 8 — Model Registry (coexistence XGBoost + GNN) ----
    # Modèles actifs en production. Valeurs acceptées :
    #   - "xgboost" : seul XGBoost sert les prédictions prod
    #   - "stgcn"   : seul GNN sert les prédictions prod
    #   - "both"    : les 2 tournent en // (GNN = challenger, XGBoost = champion)
    # Quand Patrice valide une solution, on bascule sur le winner seul.
    models_active: str = Field(default="both", alias="LYONFLOW_MODELS_ACTIVE")
    # ---- Sprint 9 — GNN training désactivé par défaut (préparation) ----
    # Quand Patrice a setup l'instance EC2 GPU et validé la solution,
    # on bascule ce toggle à True pour activer le retrain nightly.
    stgcn_training_enabled: bool = Field(default=False, alias="LYONFLOW_STGCN_TRAINING")
    # Activer l'entraînement nightly XGBoost (toujours actif sur VPS).
    xgboost_training_enabled: bool = Field(default=True, alias="LYONFLOW_XGBOOST_TRAINING")
    # ---- Sprint 9 — Dashboards préparés mais désactivés par défaut ----
    # Carte GNN géographique (visualisation des prédictions spatiales).
    # Préparée dans Pro_7_Model_Monitoring, masquée par défaut.
    gnn_map_visible: bool = Field(default=False, alias="LYONFLOW_DASHBOARD_GNN_MAP")
    # Dashboard Model Monitoring complet (lit MLflow live).
    # Préparé dans Pro_7_Model_Monitoring, masqué par défaut.
    model_monitoring_visible: bool = Field(default=False, alias="LYONFLOW_DASHBOARD_MODEL_MONITORING")


class LyonGeoSettings(BaseSettings):
    """Coordonnées Lyon centre (par défaut)."""

    latitude: float = 45.7640
    longitude: float = 4.8357


class AlertSettings(BaseSettings):
    """Alerting."""

    webhook_url: str | None = Field(default=None, alias="LYONFLOW_ALERT_WEBHOOK_URL")
    log_file: str = "/app/logs/alerts.log"


class Settings(BaseSettings):
    """Settings agrégés."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_version: str = "0.1.0"
    debug: bool = False

    db: DatabaseSettings = DatabaseSettings()
    minio: MinioSettings = MinioSettings()
    gdrive: GoogleDriveSettings = GoogleDriveSettings()
    redis: RedisSettings = RedisSettings()
    mlflow: MLflowSettings = MLflowSettings()
    api: APISettings = APISettings()
    airflow: AirflowSettings = AirflowSettings()
    ml: MLSettings = MLSettings()
    lyon: LyonGeoSettings = LyonGeoSettings()
    alerts: AlertSettings = AlertSettings()

    def is_production(self) -> bool:
        return self.app_env == "production"


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton settings (lazy init)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Validation au boot
def validate_settings() -> None:
    """Vérifie que les settings critiques sont définis. Lève RuntimeError sinon."""
    s = get_settings()
    missing = []

    if not s.db.password:
        missing.append("POSTGRES_PASSWORD")
    if not s.minio.root_password:
        missing.append("MINIO_ROOT_PASSWORD")
    if s.app_env == "production" and not s.api.key:
        missing.append("LYONFLOW_API_KEY (required in production)")
    if s.app_env == "production" and not s.airflow.admin_password:
        missing.append("AIRFLOW_ADMIN_PASSWORD (required in production)")

    if missing:
        raise RuntimeError(f"Variables d'environnement manquantes : {', '.join(missing)}")
