"""ML models — package init."""

from src.models.xgboost_speed import XGBoostSpeedModel
from src.models.xgboost_velov import XGBoostVelovModel

__all__ = [
    "XGBoostSpeedModel",
    "XGBoostVelovModel",
]
