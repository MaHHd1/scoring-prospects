"""Entraîne le modèle Lasso de prédiction de bank_asset_value.

Le modèle utilise les 5 variables retenues dans le projet :
- income_annum
- luxury_assets_value
- loan_amount
- commercial_assets_value
- residential_assets_value

Le pipeline traite les valeurs aberrantes de residential_assets_value,
impute les valeurs manquantes par la médiane, standardise les variables,
puis applique Lasso Regression.

Usage :
    python train_model.py chemin/vers/loan_approval_dataset.csv

Le fichier modele_lasso.joblib sera créé dans le dossier de ce script.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Lasso
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent
TARGET = "bank_asset_value"
FEATURES = [
    "income_annum",
    "luxury_assets_value",
    "loan_amount",
    "commercial_assets_value",
    "residential_assets_value",
]
ALPHA = 1.0
MAX_ITER = 10000


def trouver_csv() -> Path:
    """Récupère le CSV donné en argument ou le cherche près du script."""
    if len(sys.argv) > 1:
        chemin = Path(sys.argv[1]).expanduser()
        if not chemin.is_file():
            raise FileNotFoundError(f"Fichier CSV introuvable : {chemin}")
        return chemin

    noms_possibles = [
        "loan_approval_dataset.csv",
        "loan approval dataset.csv",
        "loan_approval.csv",
    ]
    for repertoire in [BASE_DIR, *BASE_DIR.parents]:
        for nom in noms_possibles:
            candidat = repertoire / nom
            if candidat.is_file():
                return candidat

    raise FileNotFoundError(
        "CSV introuvable. Placez loan_approval_dataset.csv à côté du script "
        "ou lancez : python train_model.py chemin/vers/loan_approval_dataset.csv"
    )


def main() -> None:
    chemin_csv = trouver_csv()
    df = pd.read_csv(chemin_csv)
    df.columns = df.columns.str.strip()

    colonnes_requises = FEATURES + [TARGET]
    manquantes = [col for col in colonnes_requises if col not in df.columns]
    if manquantes:
        raise ValueError(
            "Colonnes absentes du CSV : "
            + ", ".join(manquantes)
            + f"\nColonnes trouvées : {df.columns.tolist()}"
        )

    # Conserver uniquement les variables sélectionnées et la cible.
    data = df[colonnes_requises].copy()

    # Les valeurs -100000 de residential_assets_value ont été identifiées
    # comme anormales dans le notebook : elles sont transformées en NaN.
    data.loc[data["residential_assets_value"] < 0, "residential_assets_value"] = np.nan

    X = data[FEATURES]
    y = pd.to_numeric(data[TARGET], errors="coerce")

    # Écarter les lignes dont la cible n'est pas exploitable.
    masque_cible_valide = y.notna() & np.isfinite(y)
    X = X.loc[masque_cible_valide].copy()
    y = y.loc[masque_cible_valide].copy()

    # Convertir les variables explicatives en numériques.
    for col in FEATURES:
        X[col] = pd.to_numeric(X[col], errors="coerce")

    pipeline = Pipeline(
        steps=[
            ("imputation", SimpleImputer(strategy="median")),
            ("standardisation", StandardScaler()),
            ("lasso", Lasso(alpha=ALPHA, max_iter=MAX_ITER)),
        ]
    )
    pipeline.fit(X, y)

    sortie = BASE_DIR / "modele_lasso.joblib"
    joblib.dump(pipeline, sortie)

    print("Dataset utilisé :", chemin_csv)
    print("Nombre d'observations entraînées :", len(X))
    print("Variables utilisées :", FEATURES)
    print("Cible :", TARGET)
    print("Modèle : Lasso Regression")
    print("alpha :", ALPHA)
    print("Fichier enregistré :", sortie)


if __name__ == "__main__":
    main()
