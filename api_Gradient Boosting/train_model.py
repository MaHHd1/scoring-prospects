"""Entraîne le pipeline « défaut de paiement » et l'enregistre pour l'API.

Reprend le notebook Siwar_Raouafi_Defaut_Paiement (sections 3 à 5) :
  - regroupement des modalités hors documentation, log des montants,
    standardisation, one-hot, 6 variables dérivées (preparation_defaut.py) ;
  - sélection de 16 variables (RFECV, section 3.4) ;
  - séparation 80/20 stratifiée, random_state = 42 ;
  - HistGradientBoostingClassifier (class_weight="balanced"), hyperparamètres
    retenus par GridSearchCV en 4.2 : max_iter=100, max_depth=3, learning_rate=0.06.

Le pipeline n'utilise que des composants scikit-learn et le module
preparation_defaut.py (placé à côté de ce script) : l'API peut recharger le fichier.

Usage :  python train_model.py   (ou  python train_model.py chemin/vers/UCI_Credit_Card.csv)
"""

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from preparation_defaut import COLONNES_ENTREE, PreparationDefaut  # noqa: E402

CIBLE = "default.payment.next.month"
RANDOM_STATE = 42

# 16 variables retenues par RFECV (section 3.4 du notebook)
VARIABLES_RETENUES = [
    "LIMIT_BAL", "BILL_AMT1", "BILL_AMT2", "BILL_AMT4",
    "PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4",
    "PAY_1", "PAY_2", "PAY_3",
    "PAY_MEAN", "PAY_MAX", "NB_RETARDS", "UTIL_1", "UTIL_MOY",
]

# Hyperparamètres retenus en 4.2 (GridSearchCV, ROC-AUC, 5 plis)
PARAMS = dict(max_iter=100, max_depth=3, learning_rate=0.06,
              class_weight="balanced", random_state=RANDOM_STATE)

# Référence du notebook (jeu de test de 6 000 clients) pour vérifier la reproduction
REFERENCE = {"roc_auc": 0.7785, "rappel": 0.6194, "precision": 0.4541, "f1": 0.5241}
TOLERANCE = 0.01


def trouver_csv() -> Path:
    """Cherche 'UCI_Credit_Card.csv' (argument, dossier du script, puis dossiers parents)."""
    if len(sys.argv) > 1:
        chemin = Path(sys.argv[1])
        if not chemin.exists():
            raise FileNotFoundError(f"Fichier introuvable : {chemin}")
        return chemin
    for repertoire in [BASE_DIR, *BASE_DIR.parents]:
        candidat = repertoire / "UCI_Credit_Card.csv"
        if candidat.exists():
            return candidat
    raise FileNotFoundError(
        "'UCI_Credit_Card.csv' introuvable. Placez-le à côté de ce script "
        "ou indiquez son chemin : python train_model.py chemin/vers/UCI_Credit_Card.csv"
    )


def main() -> None:
    csv = trouver_csv()
    df = pd.read_csv(csv)
    print("Dataset :", csv, "|", df.shape)

    X, y = df[COLONNES_ENTREE], df[CIBLE]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=RANDOM_STATE
    )

    pipeline = Pipeline([
        ("preparation", PreparationDefaut(variables=VARIABLES_RETENUES)),
        ("modele", HistGradientBoostingClassifier(**PARAMS)),
    ])
    pipeline.fit(X_train, y_train)

    proba = pipeline.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)
    obtenu = {
        "roc_auc": roc_auc_score(y_test, proba),
        "rappel": recall_score(y_test, pred),
        "precision": precision_score(y_test, pred),
        "f1": f1_score(y_test, pred),
    }

    print(f"\nApprentissage : {len(X_train)} clients | Test : {len(X_test)} clients")
    ok = True
    for nom, ref in REFERENCE.items():
        proche = abs(obtenu[nom] - ref) <= TOLERANCE
        ok &= proche
        print(f"  {nom:<10} obtenu {obtenu[nom]:.4f} | notebook {ref:.4f} | {'OK' if proche else 'ÉCART'}")

    sortie = BASE_DIR / "modele_defaut_paiement.joblib"
    joblib.dump(pipeline, sortie)
    print("\nModèle enregistré :", sortie)

    if not ok:
        print("Les métriques s'écartent du notebook : vérifier le CSV et les versions des bibliothèques.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
