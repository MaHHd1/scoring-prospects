"""Site web de la banque - Espace conseiller.

Le site ne contient aucun modèle. Il lit apis.json (adresses des API du groupe), demande à chaque API
qui elle est et quels champs elle attend (GET /api/info), construit le formulaire avec ces champs,
puis envoie la fiche à l'API choisie (POST /api/predict) ou à toutes pour comparer.

Lancer :  python site.py     puis ouvrir http://127.0.0.1:5000
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, jsonify, render_template, request
from lasso_route import lasso_bp

app = Flask(__name__)
app.register_blueprint(lasso_bp)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANQUE = os.environ.get("BANQUE", "Banque Atlas")


def api_urls():
    """Relue à chaque appel : ajouter une ligne dans apis.json ne demande pas de redémarrer le site."""
    with open(os.path.join(BASE_DIR, "apis.json"), encoding="utf-8") as f:
        return [a["url"].rstrip("/") for a in json.load(f)["apis"]]


def lire_api(i, url):
    try:
        r = requests.get(url + "/api/info", timeout=3)
        r.raise_for_status()
        return {"index": i, "url": url, "en_ligne": True, **r.json()}
    except Exception as e:
        return {"index": i, "url": url, "en_ligne": False, "erreur": type(e).__name__}


def lire_toutes():
    urls = api_urls()
    with ThreadPoolExecutor(max_workers=max(1, len(urls))) as ex:
        return list(ex.map(lambda t: lire_api(*t), enumerate(urls)))


def scorer(modele, donnees):
    """Envoie à une API uniquement les champs qu'elle déclare."""
    base = {"index": modele["index"], "nom": modele.get("nom", modele["url"]), "auteur": modele.get("auteur", "")}
    if not modele["en_ligne"]:
        return {**base, "ok": False, "erreurs": ["API hors ligne"]}
    champs = [c["nom"] for c in modele["champs"]]
    manquants = [c for c in champs if donnees.get(c) in (None, "")]
    if manquants:
        return {**base, "ok": False, "erreurs": ["Champs manquants : " + ", ".join(manquants)]}
    try:
        r = requests.post(modele["url"] + "/api/predict", json={c: donnees[c] for c in champs}, timeout=15)
        corps = r.json()
    except Exception as e:
        return {**base, "ok": False, "erreurs": ["API injoignable (" + type(e).__name__ + ")"]}
    if r.status_code != 200:
        return {**base, "ok": False, "erreurs": corps.get("erreurs", ["Erreur " + str(r.status_code)])}
    return {**base, "ok": True, **corps}


@app.get("/")
def accueil():
    return render_template("index.html", banque=BANQUE)


@app.get("/api/models")
def modeles():
    return jsonify(lire_toutes())


@app.post("/api/score")
def score():
    """Corps : {"indices": [0] ou [0, 1, ...], "donnees": {champ: valeur}} -> un résultat par modèle."""
    corps = request.get_json(silent=True) or {}
    indices, donnees = corps.get("indices", []), corps.get("donnees", {})
    par_index = {m["index"]: m for m in lire_toutes()}
    choisis = [par_index[i] for i in indices if i in par_index]
    if not choisis:
        return jsonify({"erreur": "Aucun modèle valide choisi"}), 400
    return jsonify([scorer(m, donnees) for m in choisis])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
