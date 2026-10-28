"""Préparation des données pour la prédiction du défaut de paiement.

Reproduit la préparation du notebook (sections 3.1 à 3.4) à partir des colonnes
brutes d'un client, sous forme d'un transformateur scikit-learn réutilisable.
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

STATUTS = [f"PAY_{i}" for i in range(1, 7)]
FACTURES = [f"BILL_AMT{i}" for i in range(1, 7)]
PAIEMENTS = [f"PAY_AMT{i}" for i in range(1, 7)]
COLONNES_ENTREE = (["LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE",
                    "PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
                   + FACTURES + PAIEMENTS)
RATIOS = ["UTIL_1", "UTIL_MOY"]


class PreparationDefaut(BaseEstimator, TransformerMixin):
    """Nettoyage, log des montants, encodage, standardisation, variables dérivées et sélection."""

    def __init__(self, variables):
        self.variables = variables

    def _valider(self, X):
        X = pd.DataFrame(X).copy()
        manquantes = [c for c in COLONNES_ENTREE if c not in X.columns]
        if manquantes:
            raise ValueError(f"Colonnes manquantes : {manquantes}")
        return X[COLONNES_ENTREE]

    def _nettoyer(self, X):
        P = X.copy()
        P["EDUCATION"] = P["EDUCATION"].replace({0: 4, 5: 4, 6: 4})
        P["MARRIAGE"] = P["MARRIAGE"].replace({0: 3})
        P = P.rename(columns={"PAY_0": "PAY_1"})
        for c in PAIEMENTS:
            P[c] = np.log1p(X[c])
        for c in FACTURES:
            P[c] = np.sign(X[c]) * np.log1p(X[c].abs())
        return P

    def _derivees(self, X, P):
        out = pd.DataFrame(index=X.index)
        out["PAY_MEAN"] = P[STATUTS].mean(axis=1)
        out["PAY_MAX"] = P[STATUTS].max(axis=1)
        out["NB_RETARDS"] = (P[STATUTS] >= 1).sum(axis=1)
        out["UTIL_1"] = X["BILL_AMT1"] / X["LIMIT_BAL"]
        out["UTIL_MOY"] = X[FACTURES].mean(axis=1) / X["LIMIT_BAL"]
        out["SOLDE_CREDITEUR"] = (X[FACTURES] < 0).any(axis=1).astype(int)
        return out

    def fit(self, X, y=None):
        X = self._valider(X)
        P = self._nettoyer(X)
        self.preprocesseur_ = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), ["LIMIT_BAL", "AGE"] + FACTURES + PAIEMENTS),
                ("cat", OneHotEncoder(drop="first", sparse_output=False, handle_unknown="ignore"),
                 ["SEX", "EDUCATION", "MARRIAGE"]),
                ("pay", "passthrough", STATUTS),
            ],
            verbose_feature_names_out=False,
        ).fit(P)
        self.scaler_ratios_ = StandardScaler().fit(self._derivees(X, P)[RATIOS])
        return self

    def transform(self, X):
        X = self._valider(X)
        P = self._nettoyer(X)
        A = pd.DataFrame(self.preprocesseur_.transform(P),
                         columns=self.preprocesseur_.get_feature_names_out(), index=X.index)
        F = self._derivees(X, P)
        F[RATIOS] = self.scaler_ratios_.transform(F[RATIOS])
        return pd.concat([A, F], axis=1)[list(self.variables)]