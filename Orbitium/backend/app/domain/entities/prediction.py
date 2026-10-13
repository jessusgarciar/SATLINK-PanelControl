"""Predicción y fallos independientes de HTTP, ORM y proveedor."""
from datetime import datetime


class PredictionInvalid(ValueError):
    pass


class PredictionUnavailable(RuntimeError):
    pass


class PredictionTimeout(PredictionUnavailable):
    pass


class PredictionCooldown(RuntimeError):
    def __init__(self, next_allowed_at: datetime) -> None:
        self.next_allowed_at = next_allowed_at
        super().__init__("Espera antes de solicitar otra predicción")
