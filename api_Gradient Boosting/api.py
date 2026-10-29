"""API de prédiction du défaut de paiement - espace conseiller (site de la banque).

Contrat imposé par scoring-prospects/site (GUIDE_EQUIPE.md) :
  GET  /api/info    -> nom, auteur, description, cible, champs
                       (le site construit son formulaire à partir de `champs`)
  POST /api/predict -> fiche client (uniquement les champs déclarés) ->
                       score_pct, cible, seuil, contacter
  GET  /api/health  -> vérification « l'API est-elle en ligne ? »

Le pipeline (modele_defaut_paiement.joblib) contient toute la préparation du notebook
(regroupement des modalités, log des montants, standardisation, variables dérivées,
sélection des 16 variables) puis le Gradient Boosting. Il est chargé avec le module
preparation_defaut.py, qui doit rester dans le même dossier que ce fichier.

Lancement : python api.py            (PORT=5002 par défaut ; PORT=5010 python api.py pour changer)
"""

import os
import sys
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))   # nécessaire pour recharger le pipeline (preparation_defaut.py)
from preparation_defaut import COLONNES_ENTREE  # noqa: E402

PORT = int(os.environ.get("PORT", 5005))   # 5001 = Random Forest, 5002 = Lasso, 5003 = Isolation Forest, 5004 = K-Means, 5005 = Gradient Boosting
HOST = os.environ.get("HOST", "0.0.0.0")

NOM_MODELE = "Défaut de paiement (Gradient Boosting)"
AUTEUR = "Siwar Raouafi"
DESCRIPTION = (
    "Probabilité qu'un client de carte de crédit ne rembourse pas le mois suivant, "
    "à partir de sa limite de crédit et de six mois d'historique (retards, factures, paiements). "
    "Gradient Boosting avec pondération des classes : le score sert à classer les clients "
    "par risque, ce n'est pas une probabilité calibrée. Aucune donnée sensible "
    "(sexe, âge, études, état civil) n'est demandée."
)
CIBLE_INFO = "Défaut de paiement le mois suivant (1 = défaut)"

SEUIL = 0.50   # seuil de décision de l'évaluation principale (à confirmer avec les coûts réels de la banque)

LIBELLES_CIBLE = {
    True: "Risque de défaut élevé",
    False: "Risque de défaut faible",
}

# Colonnes que le pipeline exige mais dont le modèle ne se sert pas (sélection de variables, 3.4) :
# le site ne les demande pas, on leur donne une valeur neutre qui n'a aucun effet sur la prédiction.
VALEURS_NEUTRES = {"SEX": 2, "EDUCATION": 2, "MARRIAGE": 1, "AGE": 35, "PAY_AMT5": 0, "PAY_AMT6": 0}

# Plages observées dans UCI_Credit_Card.csv (df.describe()) et valeur par défaut (médiane).
# nom -> (libellé affiché, min, max, entier, défaut)
VARIABLES = {
    "LIMIT_BAL": ("Limite de crédit", 10000, 1000000, False, 140000),
    "PAY_0": ("Statut de paiement, mois 1 (le plus récent)", -2, 8, True, 0),
    "PAY_2": ("Statut de paiement, mois 2", -2, 8, True, 0),
    "PAY_3": ("Statut de paiement, mois 3", -2, 8, True, 0),
    "PAY_4": ("Statut de paiement, mois 4", -2, 8, True, 0),
    "PAY_5": ("Statut de paiement, mois 5", -2, 8, True, 0),
    "PAY_6": ("Statut de paiement, mois 6 (le plus ancien)", -2, 8, True, 0),
    "BILL_AMT1": ("Montant de la facture, mois 1 (le plus récent)", -165580, 964511, False, 22381),
    "BILL_AMT2": ("Montant de la facture, mois 2", -69777, 983931, False, 21200),
    "BILL_AMT3": ("Montant de la facture, mois 3", -157264, 1664089, False, 20088),
    "BILL_AMT4": ("Montant de la facture, mois 4", -170000, 891586, False, 19052),
    "BILL_AMT5": ("Montant de la facture, mois 5", -81334, 927171, False, 18104),
    "BILL_AMT6": ("Montant de la facture, mois 6 (le plus ancien)", -339603, 961664, False, 17071),
    "PAY_AMT1": ("Montant payé, mois 1 (le plus récent)", 0, 873552, False, 2100),
    "PAY_AMT2": ("Montant payé, mois 2", 0, 1684259, False, 2009),
    "PAY_AMT3": ("Montant payé, mois 3", 0, 896040, False, 1800),
    "PAY_AMT4": ("Montant payé, mois 4", 0, 621000, False, 1500),
}

# --------------------------------------------------------------------------
# Chargement du modèle
# --------------------------------------------------------------------------
CHEMIN_MODELE = BASE_DIR / "modele_defaut_paiement.joblib"
if not CHEMIN_MODELE.exists():
    raise FileNotFoundError(
        f"{CHEMIN_MODELE.name} introuvable : lancez d'abord  python train_model.py  dans ce dossier."
    )
MODELE = joblib.load(CHEMIN_MODELE)

FEATURES = list(VARIABLES)   # champs demandés au site (17)
assert set(FEATURES) | set(VALEURS_NEUTRES) == set(COLONNES_ENTREE), \
    "VARIABLES et VALEURS_NEUTRES ne couvrent pas les colonnes attendues par le pipeline"

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


def valider(corps):
    """Renvoie (valeurs, erreurs, avertissements). Erreurs = refus ; avertissements = hors plage vue."""
    valeurs, erreurs, avertissements = {}, [], []
    for nom in FEATURES:
        libelle = VARIABLES[nom][0]
        brut = corps[nom]
        try:
            v = float(brut)
        except (TypeError, ValueError):
            erreurs.append(f"{libelle} : valeur numérique attendue (reçu {brut!r})")
            continue
        if v != v or v in (float("inf"), float("-inf")):
            erreurs.append(f"{libelle} : valeur numérique attendue (reçu {brut!r})")
            continue
        if nom.startswith("PAY_") and not nom.startswith("PAY_AMT"):
            if v != int(v) or not -2 <= v <= 8:
                erreurs.append(f"{libelle} : entier entre -2 et 8 attendu (reçu {brut!r})")
                continue
        elif nom == "LIMIT_BAL" and v <= 0:
            erreurs.append(f"{libelle} : doit être strictement positive (reçu {brut!r})")
            continue
        elif nom.startswith("PAY_AMT") and v < 0:
            erreurs.append(f"{libelle} : doit être positif ou nul (reçu {brut!r})")
            continue
        if not VARIABLES[nom][1] <= v <= VARIABLES[nom][2]:
            avertissements.append(f"{libelle} : hors de l'étendue vue à l'entraînement "
                                  f"({VARIABLES[nom][1]} à {VARIABLES[nom][2]})")
        valeurs[nom] = v
    return valeurs, erreurs, avertissements


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
            "variables": len(FEATURES),
            "seuil": SEUIL,
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

    valeurs, erreurs, avertissements = valider(corps)
    if erreurs:
        return jsonify({"erreurs": erreurs}), 400

    ligne = {**VALEURS_NEUTRES, **valeurs}
    X = pd.DataFrame([ligne], columns=COLONNES_ENTREE)
    proba = float(MODELE.predict_proba(X)[0, 1])
    alerte = proba >= SEUIL

    reponse = {
        "score_pct": round(proba * 100, 1),
        "cible": LIBELLES_CIBLE[alerte],
        "seuil": SEUIL,
        "contacter": alerte,
    }
    if avertissements:
        reponse["avertissements"] = avertissements
    return jsonify(reponse)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
