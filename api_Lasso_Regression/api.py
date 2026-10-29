"""API Flask pour prédire bank_asset_value avec Lasso Regression.

Endpoints :
    GET  /api/health  -> état de l'API
    GET  /api/info    -> description du modèle et champs du formulaire
    POST /api/predict -> prédiction à partir des 5 variables du projet

Avant le lancement, créer modele_lasso.joblib avec train_model.py.

Lancement :
    python api.py

Port par défaut : 5002 (modifiable avec la variable d'environnement PORT).
"""

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 5002))
HOST = os.environ.get("HOST", "0.0.0.0")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", BASE_DIR / "modele_lasso.joblib"))

NOM_MODELE = "Lasso Regression"
AUTEUR = "Souha Mabrouk"
DESCRIPTION = (
    "Modèle de régression supervisée entraîné pour estimer la valeur des actifs "
    "bancaires d'un client à partir de cinq variables financières. "
    "Le pipeline inclut l'imputation médiane, la standardisation et Lasso Regression."
)
CIBLE = "bank_asset_value — valeur estimée des actifs bancaires"

# Les bornes et valeurs par défaut sont indicatives, basées sur le domaine
# des variables du dataset. Elles servent à construire un formulaire côté interface.
VARIABLES = {
    "income_annum": {
        "libelle": "Revenu annuel",
        "min": 0,
        "max": 100000000,
        "entier": True,
        "defaut": 5000000,
    },
    "luxury_assets_value": {
        "libelle": "Valeur des actifs de luxe",
        "min": 0,
        "max": 100000000,
        "entier": True,
        "defaut": 5000000,
    },
    "loan_amount": {
        "libelle": "Montant du prêt",
        "min": 0,
        "max": 100000000,
        "entier": True,
        "defaut": 5000000,
    },
    "commercial_assets_value": {
        "libelle": "Valeur des actifs commerciaux",
        "min": 0,
        "max": 100000000,
        "entier": True,
        "defaut": 3000000,
    },
    "residential_assets_value": {
        "libelle": "Valeur des actifs résidentiels",
        "min": 0,
        "max": 100000000,
        "entier": True,
        "defaut": 3000000,
    },
}
FEATURES = list(VARIABLES.keys())

app = Flask(__name__)

if not MODEL_PATH.is_file():
    MODELE = None
else:
    MODELE = joblib.load(MODEL_PATH)


@app.get("/api/health")
def health():
    return jsonify({
        "statut": "ok" if MODELE is not None else "modele_absent",
        "modele": NOM_MODELE,
        "fichier_modele_present": MODELE is not None,
        "variables": len(FEATURES),
    }), (200 if MODELE is not None else 503)


@app.get("/api/info")
def info():
    champs = [
        {
            "nom": nom,
            "libelle": config["libelle"],
            "type": "nombre",
            "min": config["min"],
            "max": config["max"],
            "entier": config["entier"],
            "defaut": config["defaut"],
        }
        for nom, config in VARIABLES.items()
    ]
    return jsonify({
        "nom": NOM_MODELE,
        "auteur": AUTEUR,
        "description": DESCRIPTION,
        "cible": CIBLE,
        "champs": champs,
        "metriques_validation_croisee": {
            "MAE_moyenne": 1299233.979,
            "RMSE_moyenne": 1710677.103,
            "R2_moyen": 0.719,
            "note": "Résultats de la validation croisée observés dans le notebook; à recalculer si les données ou paramètres changent."
        },
    })


@app.post("/api/predict")
def predict():
    if MODELE is None:
        return jsonify({
            "erreurs": [
                "Le modèle est absent. Exécutez d'abord train_model.py pour créer modele_lasso.joblib."
            ]
        }), 503

    corps = request.get_json(silent=True)
    if not isinstance(corps, dict):
        return jsonify({"erreurs": ["Le corps de la requête doit être un objet JSON."]}), 400

    manquants = [nom for nom in FEATURES if corps.get(nom) in (None, "")]
    if manquants:
        return jsonify({"erreurs": ["Champs manquants : " + ", ".join(manquants)]}), 400

    valeurs = {}
    erreurs = []
    for nom in FEATURES:
        brut = corps[nom]
        try:
            valeur = float(brut)
        except (TypeError, ValueError):
            erreurs.append(f"{VARIABLES[nom]['libelle']} : une valeur numérique est attendue.")
            continue

        if not np.isfinite(valeur):
            erreurs.append(f"{VARIABLES[nom]['libelle']} : la valeur doit être finie.")
        elif valeur < 0:
            erreurs.append(f"{VARIABLES[nom]['libelle']} : la valeur ne peut pas être négative.")
        else:
            valeurs[nom] = valeur

    if erreurs:
        return jsonify({"erreurs": erreurs}), 400

    X = pd.DataFrame([valeurs], columns=FEATURES)
    prediction = float(MODELE.predict(X)[0])

    return jsonify({
        "modele": NOM_MODELE,
        "cible": CIBLE,
        "prediction": round(prediction, 2),
        "score_pct": round(prediction, 2),
        "unite": "même unité monétaire que bank_asset_value dans le dataset",
    })


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
