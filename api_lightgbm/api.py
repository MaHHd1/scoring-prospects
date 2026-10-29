"""API de scoring LightGBM - Ciblage campagne dépôt à terme (Bank Marketing).

Contrat commun à toutes les API du groupe (GUIDE_EQUIPE.md) :
  GET  /api/info     -> nom, auteur, description, cible, champs
  GET  /api/health   -> {"status": "ok"}
  POST /api/predict  -> JSON {champ: valeur, ...} -> score_pct, seuil, décision

Le pipeline utilise le dataset Bank Marketing UCI.
Si modele_lightgbm.joblib est présent il est chargé, sinon un modèle de démonstration
(régression logistique calibrée) répond à sa place.

Lancer : python api.py     (PORT=5005 python api.py pour changer)
"""
import json
import math
import os
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 5005))

NOM_MODELE   = "LightGBM · Ciblage dépôt à terme"
AUTEUR       = "Membre 4"
DESCRIPTION  = (
    "Gradient Boosting (LightGBM) entraîné sur le dataset Bank Marketing UCI. "
    "Prédit la probabilité qu'un client souscrive à un dépôt à terme suite à un appel "
    "téléphonique. Variables : profil socio-démographique + historique de campagne."
)
CIBLE_INFO   = "Probabilité de souscription à un dépôt à terme"
DEFAULT_SEUIL = 0.609

# ── Champs déclarés (le site construit son formulaire avec) ─────────────────
CHAMPS = [
    {"nom": "age",       "libelle": "Âge",                          "type": "nombre", "min": 18,    "max": 100,  "entier": True,  "defaut": 40},
    {"nom": "job",       "libelle": "Métier",                       "type": "choix",
     "options": ["admin.", "blue-collar", "entrepreneur", "housemaid", "management",
                 "retired", "self-employed", "services", "student", "technician",
                 "unemployed", "unknown"], "defaut": "management"},
    {"nom": "marital",   "libelle": "Situation familiale",          "type": "choix",
     "options": ["married", "single", "divorced"], "defaut": "married"},
    {"nom": "education", "libelle": "Niveau d'éducation",           "type": "choix",
     "options": ["primary", "secondary", "tertiary", "unknown"], "defaut": "secondary"},
    {"nom": "default",   "libelle": "Défaut de paiement",          "type": "choix",
     "options": ["no", "yes"], "defaut": "no"},
    {"nom": "balance",   "libelle": "Solde annuel moyen (€)",       "type": "nombre", "min": -20000, "max": 500000, "entier": True, "defaut": 1000},
    {"nom": "housing",   "libelle": "Crédit logement",              "type": "choix",
     "options": ["no", "yes"], "defaut": "no"},
    {"nom": "loan",      "libelle": "Crédit personnel",             "type": "choix",
     "options": ["no", "yes"], "defaut": "no"},
    {"nom": "contact",   "libelle": "Canal de contact",             "type": "choix",
     "options": ["cellular", "telephone", "unknown"], "defaut": "cellular"},
    {"nom": "day",       "libelle": "Jour du dernier contact",      "type": "nombre", "min": 1,     "max": 31,   "entier": True,  "defaut": 15},
    {"nom": "month",     "libelle": "Mois du dernier contact",      "type": "choix",
     "options": ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"],
     "defaut": "may"},
    {"nom": "campaign",  "libelle": "Appels cette campagne",        "type": "nombre", "min": 1,     "max": 60,   "entier": True,  "defaut": 1},
    {"nom": "pdays",     "libelle": "Jours depuis campagne précédente (-1 = jamais)", "type": "nombre", "min": -1, "max": 900, "entier": True, "defaut": -1},
    {"nom": "previous",  "libelle": "Contacts avant cette campagne","type": "nombre", "min": 0,     "max": 60,   "entier": True,  "defaut": 0},
    {"nom": "poutcome",  "libelle": "Résultat campagne précédente", "type": "choix",
     "options": ["unknown", "success", "failure", "other"], "defaut": "unknown"},
]

FEATURES = [c["nom"] for c in CHAMPS]
BY_NAME  = {c["nom"]: c for c in CHAMPS}

# ── Chargement du modèle (optionnel) ────────────────────────────────────────
_model    = None
_seuil    = DEFAULT_SEUIL
_mode     = "demo"
_model_path = BASE_DIR / "modele_lightgbm.joblib"
_meta_path  = BASE_DIR / "modele_lightgbm.json"

if _model_path.exists():
    import joblib
    _model = joblib.load(_model_path)
    _mode  = "model"
    if _meta_path.exists():
        _seuil = float(json.loads(_meta_path.read_text(encoding="utf-8")).get("seuil_decision", DEFAULT_SEUIL))

# ── Modèle de démonstration ──────────────────────────────────────────────────
_W_DEMO = {
    "poutcome": {"success": 3.4, "failure": -0.35, "other": 0.1, "unknown": -0.25},
    "month":    {"jan": -0.6, "feb": 0.0, "mar": 1.9, "apr": 0.5, "may": -0.85,
                 "jun": -0.1, "jul": -0.45, "aug": -0.45, "sep": 1.4,
                 "oct": 1.5, "nov": -0.4, "dec": 1.3},
    "contact":  {"cellular": 0.45, "telephone": 0.2, "unknown": -1.0},
    "housing":  {"yes": -0.55, "no": 0.15},
    "loan":     {"yes": -0.4,  "no": 0.05},
    "default":  {"yes": -0.3,  "no": 0.0},
    "marital":  {"single": 0.15, "married": -0.12, "divorced": 0.0},
    "education":{"tertiary": 0.25, "secondary": 0.0, "primary": -0.15, "unknown": 0.05},
    "job": {"student": 0.7, "retired": 0.6, "unemployed": 0.2, "management": 0.15,
            "admin.": 0.0, "technician": 0.0, "self-employed": 0.05,
            "entrepreneur": -0.1, "services": -0.15, "housemaid": -0.2,
            "blue-collar": -0.4, "unknown": 0.0},
}
_DEMO_SCALE = 0.438
_DEMO_BIAS  = 0.75


def _demo_predict(c: dict) -> float:
    z = -1.9
    for k, tbl in _W_DEMO.items():
        z += tbl.get(str(c[k]), 0.0)
    age = int(c["age"])
    z += 0.35 if (age < 25 or age > 60) else 0.0
    bal = int(c["balance"])
    z += 0.45 * math.tanh(math.log10(max(bal, 0) + 1) - 2.5) if bal > 0 else -0.2
    z += -0.18 * min(int(c["campaign"]) - 1, 6)
    pd_ = int(c["pdays"])
    z += 0.8 if 0 < pd_ < 200 else (0.0 if pd_ < 0 else -0.1)
    z += 0.12 * min(int(c["previous"]), 4)
    day = int(c["day"])
    z += 0.15 if day in (1, 2, 3, 10, 30, 31) else (-0.1 if 5 <= day <= 8 else 0.0)
    return 1 / (1 + math.exp(-(_DEMO_SCALE * z + _DEMO_BIAS)))


def _ml_predict(c: dict) -> float:
    import pandas as pd
    X = pd.DataFrame([c])[FEATURES]
    return float(_model.predict_proba(X)[0, 1])


# ── Validation ───────────────────────────────────────────────────────────────
def validate(data: dict):
    row, errors = {}, []
    for f in FEATURES:
        c = BY_NAME[f]
        v = data.get(f)
        if v is None or v == "":
            errors.append(f"Champ manquant : {f}")
            continue
        if c["type"] == "nombre":
            try:
                x = float(v)
            except (TypeError, ValueError):
                errors.append(f"{c['libelle']} : nombre attendu (reçu {v!r})")
                continue
            if not (c["min"] <= x <= c["max"]):
                errors.append(f"{c['libelle']} : doit être entre {c['min']} et {c['max']}")
            row[f] = int(x) if c.get("entier") else x
        else:
            if str(v) not in c["options"]:
                errors.append(f"Valeur inconnue pour {f} : {v!r}")
            row[f] = str(v)
    return row, errors


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "mode": _mode})


@app.get("/api/info")
def info():
    return jsonify({
        "nom":         NOM_MODELE,
        "auteur":      AUTEUR,
        "description": DESCRIPTION,
        "cible":       CIBLE_INFO,
        "seuil":       round(_seuil, 3),
        "champs":      CHAMPS,
    })


@app.post("/api/predict")
def predict():
    data = request.get_json(silent=True) or {}
    row, errors = validate(data)
    if errors:
        return jsonify({"erreurs": errors}), 400
    score = _ml_predict(row) if _model is not None else _demo_predict(row)
    return jsonify({
        "modele_nom": NOM_MODELE,
        "auteur":     AUTEUR,
        "cible":      CIBLE_INFO,
        "score":      round(score, 4),
        "score_pct":  round(score * 100, 1),
        "seuil":      round(_seuil, 3),
        "contacter":  bool(score >= _seuil),
    })


if __name__ == "__main__":
    print(f"API '{NOM_MODELE}' ({AUTEUR}) sur le port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
