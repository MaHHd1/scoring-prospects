"""LightGBM scoring.

- Si `modele_final_membre4.joblib` (+ .json) est présent dans ce dossier, le vrai pipeline LightGBM est utilisé.
- Sinon, un modèle de DÉMONSTRATION (régression logistique à coefficients fixés à la main, calée sur les
  exemples du notebook et sur l'ordre d'importance des variables) répond à sa place.
"""
import json
import logging
import math
import pickle
from pathlib import Path

HERE = Path(__file__).parent
MODEL_PATH = HERE / "modele_final_membre4.joblib"
META_PATH = HERE / "modele_final_membre4.json"
LOGGER = logging.getLogger(__name__)

FEATURES = ["age", "job", "marital", "education", "default", "balance", "housing", "loan",
            "contact", "day", "month", "campaign", "pdays", "previous", "poutcome"]

DEFAULT_THRESHOLD = 0.609

_model = None
_threshold = DEFAULT_THRESHOLD
MODE = "demo"

if MODEL_PATH.exists():
    try:
        import joblib
        import pandas as pd  # noqa: F401

        loaded_model = joblib.load(MODEL_PATH)
        if not callable(getattr(loaded_model, "predict_proba", None)):
            raise TypeError("loaded model does not provide predict_proba")
    except (ImportError, OSError, EOFError, ValueError, TypeError, AttributeError, pickle.UnpicklingError) as error:
        LOGGER.warning(
            "Could not load %s (%s: %s); using demo scoring",
            MODEL_PATH,
            type(error).__name__,
            error,
        )
    else:
        _model = loaded_model
        MODE = "model"
        if META_PATH.exists():
            try:
                _threshold = float(
                    json.loads(META_PATH.read_text(encoding="utf-8")).get(
                        "seuil_decision", DEFAULT_THRESHOLD
                    )
                )
            except (OSError, ValueError, TypeError, AttributeError) as error:
                LOGGER.warning(
                    "Could not load threshold metadata %s (%s: %s); using default threshold %.3f",
                    META_PATH,
                    type(error).__name__,
                    error,
                    DEFAULT_THRESHOLD,
                )


def threshold() -> float:
    return _threshold


# ---------------------------------------------------------------- modèle de démonstration
_W = {
    "poutcome": {"success": 3.4, "failure": -0.35, "other": 0.1, "unknown": -0.25},
    "month": {"jan": -0.6, "feb": 0.0, "mar": 1.9, "apr": 0.5, "may": -0.85, "jun": -0.1, "jul": -0.45,
              "aug": -0.45, "sep": 1.4, "oct": 1.5, "nov": -0.4, "dec": 1.3},
    "contact": {"cellular": 0.45, "telephone": 0.2, "unknown": -1.0},
    "housing": {"yes": -0.55, "no": 0.15},
    "loan": {"yes": -0.4, "no": 0.05},
    "default": {"yes": -0.3, "no": 0.0},
    "marital": {"single": 0.15, "married": -0.12, "divorced": 0.0},
    "education": {"tertiary": 0.25, "secondary": 0.0, "primary": -0.15, "unknown": 0.05},
    "job": {"student": 0.7, "retired": 0.6, "unemployed": 0.2, "management": 0.15, "admin.": 0.0,
            "technician": 0.0, "self-employed": 0.05, "entrepreneur": -0.1, "services": -0.15,
            "housemaid": -0.2, "blue-collar": -0.4, "unknown": 0.0},
}


def _demo_proba(c: dict) -> float:
    z = -1.9
    for k, tbl in _W.items():
        z += tbl.get(c[k], 0.0)
    age = c["age"]
    z += 0.35 if (age < 25 or age > 60) else 0.0
    z += 0.45 * math.tanh(math.log10(max(c["balance"], 0) + 1) - 2.5) if c["balance"] > 0 else -0.2
    z += -0.18 * min(c["campaign"] - 1, 6)
    z += 0.8 if 0 < c["pdays"] < 200 else (0.0 if c["pdays"] < 0 else -0.1)
    z += 0.12 * min(c["previous"], 4)
    z += 0.15 if c["day"] in (1, 2, 3, 10, 30, 31) else (-0.1 if 5 <= c["day"] <= 8 else 0.0)
    return 1 / (1 + math.exp(-(_DEMO_SCALE * z + _DEMO_BIAS)))


_DEMO_SCALE = 0.438
_DEMO_BIAS = 0.75


def predict(client: dict) -> float:
    if _model is not None:
        import pandas as pd
        X = pd.DataFrame([client])[FEATURES]
        return float(_model.predict_proba(X)[0, 1])
    return _demo_proba(client)
