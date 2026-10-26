
"""API de scoring (Flask) - UN modèle par API, générée depuis le notebook de son auteur.

Contrat commun à toutes les API du groupe (les variables, elles, sont propres à chaque modèle) :
  GET  /api/info     identité du modèle + description de ses champs de saisie (le site construit son formulaire avec)
  GET  /api/health   {"status": "ok"}
  POST /api/predict  JSON {champ: valeur, ...} -> score, seuil, décision

Lancer :  python api.py     (port choisi dans le notebook ; pour le changer :  PORT=5002 python api.py)
"""
import os

import joblib
import pandas as pd
from flask import Flask, jsonify, request

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
bundle = joblib.load(os.path.join(BASE_DIR, "modele.joblib"))   # chargé UNE SEULE FOIS au démarrage
MODEL = bundle["modele"]            # pipeline complet : prétraitement + modèle
THRESHOLD = bundle["seuil"]         # seuil de décision choisi en phase de Modeling
FEATURES = bundle["variables"]      # variables brutes attendues par le pipeline
CHAMPS = bundle["champs"]           # description de chaque champ (type, bornes ou options, valeur par défaut)
PORT = int(os.environ.get("PORT", bundle.get("port", 5001)))
BY_NAME = {c["nom"]: c for c in CHAMPS}


def validate(data):
    """Vérifie chaque champ d'après sa description. Renvoie (ligne propre, liste d'erreurs)."""
    row, errors = {}, []
    for f in FEATURES:
        c, v = BY_NAME[f], data.get(f)
        if v is None or v == "":
            errors.append("Champ manquant : " + f)
        elif c["type"] == "nombre":
            try:
                x = float(v)
            except (TypeError, ValueError):
                errors.append(f + " doit être un nombre")
                continue
            if not c["min"] <= x <= c["max"]:
                errors.append(f + " doit être entre " + str(c["min"]) + " et " + str(c["max"]))
            row[f] = int(x) if c.get("entier") else x
        else:
            if str(v) not in c["options"]:
                errors.append("Valeur inconnue pour " + f + " : " + str(v))
            row[f] = str(v)
    return row, errors


@app.get("/api/info")
def info():
    """Identité du modèle et champs de saisie : le site s'en sert pour remplir sa liste et son formulaire."""
    return jsonify({"nom": bundle["nom"], "auteur": bundle.get("auteur", ""),
                    "description": bundle.get("description", ""), "cible": bundle.get("cible", "Score du modèle"),
                    "seuil": round(THRESHOLD, 3), "sklearn_version": bundle.get("sklearn_version", "?"),
                    "champs": CHAMPS})


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/predict")
def predict():
    data = request.get_json(silent=True) or {}
    row, errors = validate(data)
    if errors:
        return jsonify({"erreurs": errors}), 400
    score = float(MODEL.predict_proba(pd.DataFrame([row])[FEATURES])[0, 1])
    return jsonify({"modele_nom": bundle["nom"], "auteur": bundle.get("auteur", ""),
                    "cible": bundle.get("cible", "Score du modèle"),
                    "score": round(score, 4), "score_pct": round(score * 100, 1),
                    "seuil": round(THRESHOLD, 3), "contacter": bool(score >= THRESHOLD)})


if __name__ == "__main__":
    print("API '" + bundle["nom"] + "' (" + bundle.get("auteur", "") + ") sur le port", PORT)
    app.run(host="0.0.0.0", port=PORT)
