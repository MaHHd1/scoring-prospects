"""Entraîne le pipeline K-Means de segmentation et l'enregistre pour l'API.

Reprend exactement Clustering_Models_Updated.ipynb :
  - CUST_ID exclu -> 17 variables comportementales ;
  - valeurs manquantes imputées par la médiane de la colonne ;
  - StandardScaler ;
  - KMeans(n_clusters=3, random_state=42, n_init=10)  (K=3 = meilleur silhouette).

Règle du GUIDE_EQUIPE : uniquement des composants scikit-learn,
aucune fonction définie dans le notebook -> l'API peut recharger le fichier.

Usage :  python train_model.py   (ou  path/vers/CC GENERAL.csv en argument)
"""

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent
N_CLUSTERS = 3          # best_k du notebook (meilleur score de silhouette)
RANDOM_STATE = 42
N_INIT = 10

# Référence du notebook pour vérifier que la reproduction est identique
TAILLES_NOTEBOOK = {0: 1275, 1: 6114, 2: 1561}
LABELS_NOTEBOOK = [1, 2, 1, 1, 1]   # C10001..C10005


def trouver_csv() -> Path:
    """Cherche 'CC GENERAL.csv' comme dans le notebook (dossier courant et parents)."""
    if len(sys.argv) > 1:
        chemin = Path(sys.argv[1])
        if not chemin.exists():
            raise FileNotFoundError(f"Fichier introuvable : {chemin}")
        return chemin
    for repertoire in [BASE_DIR, *BASE_DIR.parents]:
        candidat = repertoire / "CC GENERAL.csv"
        if candidat.exists():
            return candidat
    raise FileNotFoundError(
        "'CC GENERAL.csv' introuvable. Placez-le à côté de ce script "
        "ou indiquez son chemin : python train_model.py chemin/vers/CC GENERAL.csv"
    )


def main() -> None:
    csv = trouver_csv()
    df = pd.read_csv(csv)

    # Étape « Data Preparation » du notebook : CUST_ID exclu, 17 variables conservées
    X_model = df.drop(columns=["CUST_ID"])
    print("Dataset :", csv)
    print("Variables (", len(X_model.columns), ") :", list(X_model.columns), sep="")

    # Même prétraitement que le notebook (fillna médiane puis StandardScaler),
    # exprimé en composants scikit-learn pour être rechargable par l'API.
    pipeline = Pipeline(
        [
            ("imputation", SimpleImputer(strategy="median")),
            ("standardisation", StandardScaler()),
            ("kmeans", KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=N_INIT)),
        ]
    )
    pipeline.fit(X_model)

    labels = pipeline.predict(X_model)
    tailles = pd.Series(labels).value_counts().sort_index().to_dict()

    print("\nTailles obtenues :", tailles)
    print("Tailles notebook  :", TAILLES_NOTEBOOK)
    print("5 premiers labels obtenus :", labels[:5].tolist())
    print("5 premiers labels notebook :", LABELS_NOTEBOOK)

    ok_tailles = tailles == TAILLES_NOTEBOOK
    ok_labels = labels[:5].tolist() == LABELS_NOTEBOOK
    print("\nVérification tailles des segments :", "OK" if ok_tailles else "ÉCART")
    print("Vérification labels des 5 premiers clients :", "OK" if ok_labels else "ÉCART")

    sortie = BASE_DIR / "modele_kmeans.joblib"
    joblib.dump(pipeline, sortie)
    print("\nModèle enregistré :", sortie)

    if not (ok_tailles and ok_labels):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
