"""API Isolation Forest - detection de transactions atypiques (espace conseiller).

Contrat impose par scoring-prospects/site (GUIDE_EQUIPE.md) :
  GET  /api/info    -> nom, auteur, description, cible, champs (le site construit son formulaire)
  POST /api/predict -> fiche transaction (champs declares) -> score_pct, cible, seuil, contacter
  GET  /api/health  -> verification « l'API est-elle en ligne ? »

Le pipeline (modele_isolation_forest.joblib) contient tout le pretraitement :
ratio montant/solde -> one-hot des categories -> IsolationForest (1000 arbres).
Il accepte directement les 8 champs bruts.

Lancement : python api.py        (PORT=5003 par defaut)
"""

import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from sklearn.exceptions import InconsistentVersionWarning

import preparation_transactions  # noqa: F401  (necessaire pour recharger le pipeline)

BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 5003))
HOST = os.environ.get("HOST", "0.0.0.0")

NOM_MODELE = "Isolation Forest - transactions atypiques"
AUTEUR = "Mehdi Dhib"
DESCRIPTION = (
    "Detection non supervisee de transactions bancaires atypiques (Isolation Forest, "
    "1000 arbres, 5 % d'alertes). Le score est un score d'atypicite : plus il est eleve, "
    "plus la transaction s'ecarte des comportements habituels. Ce n'est pas une probabilite "
    "de fraude (aucune etiquette de fraude dans les donnees)."
)
CIBLE_INFO = "Score d'atypicite de la transaction"
CIBLE_ALERTE = "Transaction atypique : a examiner"
CIBLE_NORMALE = "Transaction habituelle"

# nom -> (libelle, min, max, entier, defaut). Bornes larges : une valeur hors du jeu
# d'apprentissage est justement ce qu'on cherche a detecter (regles de la section 1.5 du notebook).
NUMERIQUES = {
    "TransactionAmount": ("Montant de la transaction", 0.01, 100000.0, False, 211.14),
    "CustomerAge": ("Age du client", 18, 100, True, 45),
    "TransactionDuration": ("Duree de la transaction (s)", 1, 3600, True, 112),
    "LoginAttempts": ("Tentatives de connexion", 1, 10, True, 1),
    "AccountBalance": ("Solde du compte", 0.01, 1000000.0, False, 4735.51),
}
CATEGORIELLES = {
    "TransactionType": ("Type de transaction", "Debit"),
    "Channel": ("Canal", "Online"),
    "CustomerOccupation": ("Profession du client", "Student"),
}

# --------------------------------------------------------------------------
# Chargement du modele
# --------------------------------------------------------------------------
FICHIER_MODELE = BASE_DIR / "modele_isolation_forest.joblib"
FICHIER_CSV = BASE_DIR / "bank_transactions_data_2.csv"


def charger_modele():
    """Charge le .joblib ; s'il est absent, illisible ou enregistre avec une autre version de
    scikit-learn, le re-entraine automatiquement depuis le CSV (quelques secondes) et le re-sauvegarde."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", InconsistentVersionWarning)
            return joblib.load(FICHIER_MODELE)
    except Exception as erreur:
        print(f"[api] Modele inutilisable ({type(erreur).__name__}) -> re-entrainement depuis le CSV...")
        if not FICHIER_CSV.exists():
            raise SystemExit(
                f"Modele inutilisable et {FICHIER_CSV.name} introuvable dans {BASE_DIR}. "
                "Placez le CSV dans ce dossier puis relancez (ou : python train_model.py)."
            )
        import train_model
        pipeline = train_model.entrainer(pd.read_csv(FICHIER_CSV))
        joblib.dump(pipeline, FICHIER_MODELE)
        print("[api] Modele re-entraine et enregistre :", FICHIER_MODELE.name)
        return pipeline


MODELE = charger_modele()
FEATURES = list(NUMERIQUES) + list(CATEGORIELLES)
IFOREST = MODELE.named_steps["isolation_forest"]
SEUIL = float(-IFOREST.offset_)           # score d'atypicite a partir duquel il y a alerte (95e centile)

_encodeur = MODELE.named_steps["preparation"].named_transformers_["cat"]
OPTIONS = {nom: [str(v) for v in cats] for nom, cats in zip(CATEGORIELLES, _encodeur.categories_)}

assert set(MODELE.feature_names_in_) == set(FEATURES), "FEATURES et modele ne couvrent pas les memes colonnes"

CHAMPS = [
    {"nom": n, "libelle": lib, "type": "nombre", "min": mn, "max": mx, "entier": ent, "defaut": dft}
    for n, (lib, mn, mx, ent, dft) in NUMERIQUES.items()
] + [
    {"nom": n, "libelle": lib, "type": "choix", "options": OPTIONS[n],
     "defaut": dft if dft in OPTIONS[n] else OPTIONS[n][0]}
    for n, (lib, dft) in CATEGORIELLES.items()
]

app = Flask(__name__)


@app.get("/api/health")
def health():
    return jsonify({"statut": "ok", "modele": NOM_MODELE, "auteur": AUTEUR,
                    "variables": len(FEATURES), "seuil": round(SEUIL, 4)})


@app.get("/api/info")
def info():
    return jsonify({"nom": NOM_MODELE, "auteur": AUTEUR, "description": DESCRIPTION,
                    "cible": CIBLE_INFO, "champs": CHAMPS})


@app.post("/api/predict")
def predict():
    corps = request.get_json(silent=True) or {}
    if not isinstance(corps, dict):
        return jsonify({"erreurs": ["Le corps de la requete doit etre un objet JSON"]}), 400

    manquants = [f for f in FEATURES if corps.get(f) in (None, "")]
    if manquants:
        return jsonify({"erreurs": ["Champs manquants : " + ", ".join(manquants)]}), 400

    erreurs, valeurs = [], {}
    for nom, (lib, mn, mx, entier, _) in NUMERIQUES.items():
        brut = corps[nom]
        try:
            v = float(brut)
        except (TypeError, ValueError):
            erreurs.append(f"{lib} : valeur numerique attendue (recu {brut!r})")
            continue
        if not np.isfinite(v) or not (mn <= v <= mx):
            erreurs.append(f"{lib} : valeur entre {mn} et {mx} attendue (recu {brut!r})")
            continue
        valeurs[nom] = v
    for nom, (lib, _) in CATEGORIELLES.items():
        v = str(corps[nom])
        if v not in OPTIONS[nom]:
            erreurs.append(f"{lib} : choisir parmi {', '.join(OPTIONS[nom])} (recu {v!r})")
            continue
        valeurs[nom] = v
    if erreurs:
        return jsonify({"erreurs": erreurs}), 400

    X = pd.DataFrame([valeurs], columns=FEATURES)
    score = float(-MODELE.score_samples(X)[0])        # score d'atypicite (0 a 1)
    alerte = score >= SEUIL

    return jsonify({
        "score_pct": round(score * 100, 1),
        "cible": CIBLE_ALERTE if alerte else CIBLE_NORMALE,
        "seuil": round(SEUIL, 4),
        "contacter": bool(alerte),     # le site affiche son badge vert quand contacter = true
        "alerte": bool(alerte),
    })


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
