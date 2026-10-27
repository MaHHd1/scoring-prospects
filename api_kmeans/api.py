"""API de segmentation K-Means - espace conseiller (site de la banque).

Contrat impose par scoring-prospects/site (GUIDE_EQUIPE.md) :
  GET  /api/info    -> nom, auteur, description, cible, champs
                       (le site construit son formulaire a partir de `champs`)
  POST /api/predict -> fiche client (uniquement les champs declares) ->
                       score_pct, cible, seuil, contacter
  GET  /api/health  -> verification « l'API est-elle en ligne ? »

Le pipeline (modele_kmeans.joblib) contient tout le pretraitement :
imputation mediane -> StandardScaler -> KMeans(k=3). Il accepte
directement les 17 variables brutes, sans fonction definie dans le notebook.

Lancement : python api.py            (PORT=5010 python api.py pour changer de port)
"""

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 5004))   # 5001-5003 reserves aux membres de l'equipe
HOST = os.environ.get("HOST", "0.0.0.0")

NOM_MODELE = "Segmentation K-Means (3 segments)"
AUTEUR = "Hedi Hassan"
DESCRIPTION = (
    "Clients regroupes en 3 segments par K-Means sur 17 variables "
    "comportementales de la carte de credit (imputation mediane + StandardScaler). "
    "Le score mesure la confiance d'appartenance au segment attribue."
)
CIBLE_INFO = "Segment de clientèle (appartenance K-Means)"

# Choix d'interpretation (modifiables ici) :
#  - le badge du site affiche « Prospect prioritaire » selon SEGMENT_PRIORITAIRE ;
#  - le score compare la confiance d'appartenance a SEUIL_CONFIANCE.
SEGMENT_PRIORITAIRE = 0   # cluster des clients aux achats elevés (14,25 % des clients)
SEUIL_CONFIANCE = 0.70    # seuil affiche par le site sous le score

SEGMENTS = [
    "Segment 0 · Achats élevés",
    "Segment 1 · Profil moyen",
    "Segment 2 · Fortes avances de trésorerie",
]

# Statistiques du dataset (df.describe() du notebook) : bornes et valeur par defaut.
# nom -> (libelle affiche, min, max, entier, defaut)
VARIABLES = {
    "BALANCE": ("Solde du compte", 0.0, 19043.14, False, 873.39),
    "BALANCE_FREQUENCY": ("Fréquence de mise à jour du solde", 0.0, 1.0, False, 1.0),
    "PURCHASES": ("Montant total des achats", 0.0, 49039.57, False, 361.28),
    "ONEOFF_PURCHASES": ("Achats en une fois", 0.0, 40761.25, False, 38.0),
    "INSTALLMENTS_PURCHASES": ("Achats échelonnés", 0.0, 22500.0, False, 89.0),
    "CASH_ADVANCE": ("Avances de trésorerie (montant)", 0.0, 47137.21, False, 0.0),
    "PURCHASES_FREQUENCY": ("Fréquence des achats", 0.0, 1.0, False, 0.5),
    "ONEOFF_PURCHASES_FREQUENCY": ("Fréquence des achats en une fois", 0.0, 1.0, False, 0.083333),
    "PURCHASES_INSTALLMENTS_FREQUENCY": ("Fréquence des achats échelonnés", 0.0, 1.0, False, 0.166667),
    "CASH_ADVANCE_FREQUENCY": ("Fréquence des avances de trésorerie", 0.0, 1.5, False, 0.0),
    "CASH_ADVANCE_TRX": ("Nombre d'avances de trésorerie", 0, 123, True, 0),
    "PURCHASES_TRX": ("Nombre d'achats", 0, 358, True, 7),
    "CREDIT_LIMIT": ("Limite de crédit", 50.0, 30000.0, False, 3000.0),
    "PAYMENTS": ("Montant des paiements", 0.0, 50721.48, False, 856.90),
    "MINIMUM_PAYMENTS": ("Paiement minimum", 0.019163, 76406.21, False, 312.34),
    "PRC_FULL_PAYMENT": ("Part du paiement total", 0.0, 1.0, False, 0.0),
    "TENURE": ("Ancienneté (mois)", 6, 12, True, 12),
}

# --------------------------------------------------------------------------
# Chargement du modele
# --------------------------------------------------------------------------
MODELE = joblib.load(BASE_DIR / "modele_kmeans.joblib")
FEATURES = list(MODELE.named_steps["imputation"].feature_names_in_)   # 17 variables brutes
PRETRAITEMENT = MODELE[:-1]                       # imputation + StandardScaler
CENTROIDES = MODELE.named_steps["kmeans"].cluster_centers_

assert len(FEATURES) == 17, f"17 variables attendues, {len(FEATURES)} trouvées"
assert set(FEATURES) == set(VARIABLES), "VARIABLES et modèle ne couvrent pas les mêmes colonnes"

CHAMPS = [
    {
        "nom": nom,
        "libelle": VARIABLES[nom][0],
        "type": "nombre",
        "min": VARIABLES[nom][1],
        "max": VARIABLES[nom][2],
        "entier": VARIABLES[nom][3],
        "defaut": VARIABLES[nom][4],
    }
    for nom in FEATURES
]

app = Flask(__name__)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify(
        {
            "statut": "ok",
            "modele": NOM_MODELE,
            "auteur": AUTEUR,
            "segments": len(SEGMENTS),
            "variables": len(FEATURES),
        }
    )


@app.get("/api/info")
def info():
    return jsonify(
        {
            "nom": NOM_MODELE,
            "auteur": AUTEUR,
            "description": DESCRIPTION,
            "cible": CIBLE_INFO,
            "champs": CHAMPS,
        }
    )


@app.post("/api/predict")
def predict():
    corps = request.get_json(silent=True) or {}
    if not isinstance(corps, dict):
        return jsonify({"erreurs": ["Le corps de la requête doit être un objet JSON"]}), 400

    manquants = [f for f in FEATURES if corps.get(f) in (None, "")]
    if manquants:
        return jsonify({"erreurs": ["Champs manquants : " + ", ".join(manquants)]}), 400

    erreurs, valeurs = [], {}
    for nom in FEATURES:
        brut = corps[nom]
        try:
            valeur = float(brut)
        except (TypeError, ValueError):
            erreurs.append(f"{VARIABLES[nom][0]} : valeur numérique attendue (reçu {brut!r})")
            continue
        if np.isnan(valeur):
            erreurs.append(f"{VARIABLES[nom][0]} : valeur numérique attendue (reçu {brut!r})")
            continue
        valeurs[nom] = valeur
    if erreurs:
        return jsonify({"erreurs": erreurs}), 400

    X = pd.DataFrame([valeurs], columns=FEATURES)
    X_scaled = PRETRAITEMENT.transform(X)

    distances = np.linalg.norm(X_scaled - CENTROIDES, axis=1)
    segment = int(np.argmin(distances))
    ordre = np.sort(distances)
    d1, d2 = float(ordre[0]), float(ordre[1])
    confiance = 1.0 if d1 + d2 == 0 else d2 / (d1 + d2)

    return jsonify(
        {
            "segment": segment,
            "score_pct": round(confiance * 100, 1),
            "cible": SEGMENTS[segment],
            "seuil": SEUIL_CONFIANCE,
            "contacter": segment == SEGMENT_PRIORITAIRE,
        }
    )


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
