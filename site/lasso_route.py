"""Module d'intégration isolé pour le modèle Lasso Regression.

Ce module n'interfère avec aucune des API ni aucun des endpoints existants.
Il fournit :
  - La page web dédiée : GET /lasso
  - Le proxy d'information : GET /api/lasso/info
  - Le proxy de santé : GET /api/lasso/health
  - Le proxy de prédiction d'actifs : POST /api/lasso/predict
"""

import os
import requests
from flask import Blueprint, jsonify, render_template, request

lasso_bp = Blueprint("lasso", __name__)
BANQUE = os.environ.get("BANQUE", "Banque Atlas")


def get_lasso_url() -> str:
    """Détermine l'URL de l'API Lasso : variable d'environnement ou détection automatique 5002 / 5004."""
    override = os.environ.get("LASSO_API_URL")
    if override:
        return override.rstrip("/")

    # Essayer le slot configuré 5002 puis 5004
    for candidate in ["http://127.0.0.1:5002", "http://127.0.0.1:5004"]:
        try:
            r = requests.get(candidate + "/api/health", timeout=0.4)
            if r.status_code == 200 and r.json().get("modele") == "Lasso Regression":
                return candidate
        except Exception:
            continue

    return "http://127.0.0.1:5002"


@lasso_bp.get("/lasso")
def page_lasso():
    return render_template("lasso.html", banque=BANQUE)


@lasso_bp.get("/api/lasso/health")
def lasso_health():
    url = get_lasso_url()
    try:
        r = requests.get(url + "/api/health", timeout=2)
        return jsonify({"en_ligne": r.status_code == 200, "url": url, **r.json()}), r.status_code
    except Exception as e:
        return jsonify({"en_ligne": False, "url": url, "erreur": type(e).__name__}), 503


@lasso_bp.get("/api/lasso/info")
def lasso_info():
    url = get_lasso_url()
    try:
        r = requests.get(url + "/api/info", timeout=3)
        r.raise_for_status()
        return jsonify({"en_ligne": True, "url": url, **r.json()})
    except Exception as e:
        return jsonify({
            "en_ligne": False,
            "url": url,
            "erreur": type(e).__name__,
            "message": "L'API Lasso Regression n'est pas joignable sur " + url
        }), 503


@lasso_bp.post("/api/lasso/predict")
def lasso_predict():
    url = get_lasso_url()
    corps = request.get_json(silent=True)
    if not isinstance(corps, dict):
        return jsonify({"ok": False, "erreurs": ["Le corps de la requête doit être un objet JSON valide."]}), 400

    champs_requis = [
        "income_annum",
        "luxury_assets_value",
        "loan_amount",
        "commercial_assets_value",
        "residential_assets_value",
    ]

    manquants = [c for c in champs_requis if corps.get(c) in (None, "")]
    if manquants:
        return jsonify({"ok": False, "erreurs": ["Champs manquants : " + ", ".join(manquants)]}), 400

    try:
        r = requests.post(url + "/api/predict", json=corps, timeout=5)
        reponse = r.json()
    except Exception as e:
        return jsonify({
            "ok": False,
            "erreurs": [f"L'API Lasso Regression ({url}) est injoignable ({type(e).__name__})."]
        }), 503

    if r.status_code != 200:
        erreurs = reponse.get("erreurs", [f"Erreur de prédiction (HTTP {r.status_code})"])
        return jsonify({"ok": False, "erreurs": erreurs}), r.status_code

    return jsonify({"ok": True, "url": url, **reponse})
