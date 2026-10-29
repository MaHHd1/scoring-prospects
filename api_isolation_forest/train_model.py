"""Entraine le pipeline Isolation Forest (detection de transactions atypiques) pour l'API.

Reprend le notebook DHIB_MEHDI (parties B, C.2 et E) :
  - colonnes inutiles ecartees (TransactionID, PreviousTransactionDate, dates, IDs a forte cardinalite) ;
  - variable creee : AmountToBalance = montant / solde ;
  - 6 variables numeriques gardees brutes (Isolation Forest n'a pas besoin de standardisation) ;
  - OneHotEncoder(drop="if_binary") sur TransactionType, Channel, CustomerOccupation -> 14 colonnes ;
  - IsolationForest(contamination=0.05) -> 5 % d'alertes, comme les 126 alertes du notebook.

Difference avec le notebook : au lieu de 10 modeles de 300 arbres (moyenne des scores), on
entraine UN seul modele de 1000 arbres. Un pipeline scikit-learn ne peut pas contenir une liste
de modeles, et un grand nombre d'arbres donne la meme stabilite (le notebook montre 0,84 a 600 arbres).
Le seuil d'alerte (95e centile des scores) est stocke par scikit-learn dans `offset_`.

Usage :  python train_model.py            (cherche bank_transactions_data_2.csv)
         python train_model.py chemin/vers/bank_transactions_data_2.csv
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

from preparation_transactions import ajouter_ratio

BASE_DIR = Path(__file__).resolve().parent
NOM_CSV = "bank_transactions_data_2.csv"

VARIABLES_BRUTES_NUM = ["TransactionAmount", "CustomerAge", "TransactionDuration",
                        "LoginAttempts", "AccountBalance"]
VARIABLES_CAT = ["TransactionType", "Channel", "CustomerOccupation"]
FEATURES_API = VARIABLES_BRUTES_NUM + VARIABLES_CAT          # 8 champs saisis dans le site
NUM_MODELE = VARIABLES_BRUTES_NUM + ["AmountToBalance"]      # 6 numeriques du notebook

N_ARBRES = 1000
CONTAMINATION = 0.05
RANDOM_STATE = 0

# Reperes du notebook pour verifier la reproduction
N_ALERTES_NOTEBOOK = 126          # 5 % de 2512
COHERENCE_MIN = 0.85              # notebook : 91 % des alertes portent un signal de reference


def trouver_csv() -> Path:
    if len(sys.argv) > 1:
        chemin = Path(sys.argv[1])
        if not chemin.exists():
            raise FileNotFoundError(f"Fichier introuvable : {chemin}")
        return chemin
    for repertoire in [BASE_DIR, *BASE_DIR.parents]:
        candidat = repertoire / NOM_CSV
        if candidat.exists():
            return candidat
    raise FileNotFoundError(
        f"'{NOM_CSV}' introuvable. Placez-le a cote de ce script "
        f"ou : python train_model.py chemin/vers/{NOM_CSV}"
    )


def signaux_reference(df: pd.DataFrame) -> pd.Series:
    """Les 4 signaux du notebook (2.4). Sert UNIQUEMENT a verifier, jamais a entrainer."""
    ratio = df["TransactionAmount"] / df["AccountBalance"]
    d = df["TransactionDuration"]
    s = (
        (df["LoginAttempts"] >= 3)
        | (df["TransactionAmount"] > df["TransactionAmount"].quantile(0.95))
        | (ratio > 1)
        | (d < d.quantile(0.02))
        | (d > d.quantile(0.98))
    )
    return s


def construire_pipeline() -> Pipeline:
    preparation = ColumnTransformer(
        [
            ("num", "passthrough", NUM_MODELE),
            ("cat", OneHotEncoder(drop="if_binary", sparse_output=False), VARIABLES_CAT),
        ]
    )
    return Pipeline(
        [
            ("ratio", FunctionTransformer(ajouter_ratio, validate=False)),
            ("preparation", preparation),
            ("isolation_forest", IsolationForest(
                n_estimators=N_ARBRES, contamination=CONTAMINATION, random_state=RANDOM_STATE)),
        ]
    )


def entrainer(df: pd.DataFrame) -> Pipeline:
    """Construit et entraine le pipeline sur les 8 colonnes brutes (utilise aussi par api.py)."""
    X = df[FEATURES_API]                      # colonnes brutes uniquement
    assert X.isna().sum().sum() == 0, "valeurs manquantes inattendues"
    pipeline = construire_pipeline()
    pipeline.fit(X)
    return pipeline


def main() -> None:
    csv = trouver_csv()
    df = pd.read_csv(csv)
    print("Dataset :", csv, df.shape)

    pipeline = entrainer(df)
    X = df[FEATURES_API]

    n_colonnes = pipeline.named_steps["preparation"].get_feature_names_out().shape[0]
    alertes = pipeline.predict(X) == -1
    sig = signaux_reference(df).to_numpy()
    coherence = float(sig[alertes].mean())

    print(f"\nColonnes apres preparation : {n_colonnes} (notebook : 14)")
    print(f"Alertes : {int(alertes.sum())} (notebook : {N_ALERTES_NOTEBOOK})")
    print(f"Alertes avec signal de reference : {coherence:.1%} (notebook : 91 %, hasard : {sig.mean():.1%})")
    print(f"Seuil d'alerte (score d'atypicite) : {-pipeline.named_steps['isolation_forest'].offset_:.4f}")

    ok = (n_colonnes == 14
          and abs(int(alertes.sum()) - N_ALERTES_NOTEBOOK) <= 3
          and coherence >= COHERENCE_MIN)
    print("\nVerification :", "OK" if ok else "ECART avec le notebook")

    sortie = BASE_DIR / "modele_isolation_forest.joblib"
    joblib.dump(pipeline, sortie)
    print("Modele enregistre :", sortie, f"({sortie.stat().st_size / 1e6:.1f} Mo)")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
