"""Données du tableau de bord bancaire : portefeuille, segments RFM et alertes.

Le tableau de bord ne remplace pas les API de modèles : il agrège le fichier de
transactions du projet (`api_isolation_forest/bank_transactions_data_2.csv`) pour
donner au conseiller une vue d'ensemble, et interroge l'API Isolation Forest
(port 5003) pour les transactions atypiques.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
FICHIER_TRANSACTIONS = BASE.parent / "api_isolation_forest" / "bank_transactions_data_2.csv"
API_ANOMALIES = os.environ.get("API_ANOMALIES_URL", "http://127.0.0.1:5003")

SEUIL_INACTIF = 90  # jours sans transaction
NB_TRANSACTIONS_EXAMINEES = 6

# Segment -> vocabulaire métier. L'ordre est celui de l'affichage.
SEGMENTS = {
    "champions": {
        "nom": "Champions",
        "resume": "Récents, fréquents et gros volumes",
        "action": "Fidéliser : offre premium, hausse de plafond",
        "couleur": "#0f766e",
    },
    "loyaux": {
        "nom": "Loyaux",
        "resume": "Réguliers, bon volume, aucune urgence",
        "action": "Développer : épargne, assurance, produits complémentaires",
        "couleur": "#1d4ed8",
    },
    "prometteurs": {
        "nom": "Prometteurs",
        "resume": "Récents mais encore peu actifs",
        "action": "Encourager l'usage : cashback temporaire, démo de l'app",
        "couleur": "#7c3aed",
    },
    "a_reveiller": {
        "nom": "À réveiller",
        "resume": "Fort volume, plus actifs depuis longtemps",
        "action": "Relancer : appel du conseiller, offre de réactivation",
        "couleur": "#b45309",
    },
    "dormants": {
        "nom": "Dormants",
        "resume": "Peu actifs et anciens",
        "action": "Réactiver par campagne, sinon archiver le compte",
        "couleur": "#64748b",
    },
}
ORDRE_SEGMENTS = ["champions", "loyaux", "prometteurs", "a_reveiller", "dormants"]

# Scores RFM calculés par quintiles : 1 = plus faible, 5 = plus fort.
def _quintiles(serie: pd.Series) -> pd.Series:
    return pd.qcut(serie.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)


def _segment(ligne) -> str:
    if ligne.R >= 4 and ligne.F >= 4:
        return "champions"
    if ligne.R <= 2 and ligne.M >= 4:
        return "a_reveiller"
    if ligne.R >= 4 and ligne.F <= 2:
        return "prometteurs"
    if ligne.R >= 3 and ligne.F >= 3:
        return "loyaux"
    return "dormants"


@lru_cache(maxsize=1)
def portefeuille() -> pd.DataFrame:
    """Une ligne par compte, avec les indicateurs RFM et le segment associé."""
    transactions = pd.read_csv(FICHIER_TRANSACTIONS, parse_dates=["TransactionDate"])
    date_reference = transactions["TransactionDate"].max()

    clients = transactions.groupby("AccountID").agg(
        derniere=("TransactionDate", "max"),
        nb=("TransactionID", "size"),
        volume=("TransactionAmount", "sum"),
        panier=("TransactionAmount", "mean"),
        occupation=("CustomerOccupation", "first"),
        age=("CustomerAge", "first"),
        solde=("AccountBalance", "mean"),
        canal=("Channel", lambda serie: serie.mode().iat[0]),
    )
    clients["recence"] = (date_reference - clients["derniere"]).dt.days
    clients["R"] = pd.qcut(-clients["recence"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    clients["F"] = _quintiles(clients["nb"])
    clients["M"] = _quintiles(clients["volume"])
    clients["segment"] = clients.apply(_segment, axis=1)
    clients["date_reference"] = date_reference
    return clients


def date_reference():
    return portefeuille()["date_reference"].iat[0]


@lru_cache(maxsize=1)
def resume() -> dict:
    """Indicateurs du portefeuille et synthèse par segment."""
    clients = portefeuille()
    transactions = pd.read_csv(FICHIER_TRANSACTIONS, parse_dates=["TransactionDate"])
    total_volume = clients["volume"].sum()

    kpis = {
        "clients": len(clients),
        "volume": total_volume,
        "panier": clients["panier"].mean(),
        "inactifs": int((clients["recence"] > SEUIL_INACTIF).sum()),
        "part_online": transactions["Channel"].eq("Online").mean(),
    }

    segments = []
    for cle in ORDRE_SEGMENTS:
        groupe = clients[clients["segment"] == cle]
        segments.append(
            {
                "cle": cle,
                **SEGMENTS[cle],
                "clients": len(groupe),
                "part_clients": len(groupe) / len(clients),
                "volume": groupe["volume"].sum(),
                "part_volume": groupe["volume"].sum() / total_volume,
                "panier": groupe["panier"].mean() if len(groupe) else 0,
                "recence": groupe["recence"].mean() if len(groupe) else 0,
            }
        )

    return {"kpis": kpis, "segments": segments}


@lru_cache(maxsize=8)
def clients_du_segment(cle: str) -> tuple[dict, ...]:
    clients = portefeuille()
    groupe = clients[clients["segment"] == cle].sort_values("volume", ascending=False)
    return tuple(_ligne_client(cle, index, ligne) for index, ligne in groupe.iterrows())


def _ligne_client(cle: str, index, ligne) -> dict:
    return {
        "cle": cle,
        "compte": index,
        "occupation": ligne["occupation"],
        "age": int(ligne["age"]),
        "derniere": ligne["derniere"].date(),
        "recence": int(ligne["recence"]),
        "nb": int(ligne["nb"]),
        "volume": round(ligne["volume"]),
        "panier": round(ligne["panier"]),
        "solde": round(ligne["solde"]),
        "canal": ligne["canal"],
        "R": int(ligne["R"]),
        "F": int(ligne["F"]),
        "M": int(ligne["M"]),
    }


def _transactions_a_examiner() -> pd.DataFrame:
    """Les transactions les plus déséquilibrées (montant / solde), une par compte."""
    transactions = pd.read_csv(FICHIER_TRANSACTIONS, parse_dates=["TransactionDate"])
    transactions["ratio"] = transactions["TransactionAmount"] / transactions["AccountBalance"].clip(lower=1)
    return (
        transactions.sort_values("ratio", ascending=False)
        .drop_duplicates("AccountID")
        .head(NB_TRANSACTIONS_EXAMINEES)
    )


_ALERTES: dict | None = None


def alertes() -> dict:
    """Score d'atypicité des transactions examinées, via l'API Isolation Forest.

    Le résultat n'est mémorisé que si l'API répond : si elle démarre plus tard,
    le prochain affichage la prend en compte sans redémarrer le tableau de bord.
    """
    global _ALERTES
    if _ALERTES is not None:
        return _ALERTES

    clients = portefeuille()
    lignes = []
    for _, transaction in _transactions_a_examiner().iterrows():
        entree = {
            "TransactionAmount": float(transaction["TransactionAmount"]),
            "CustomerAge": int(transaction["CustomerAge"]),
            "TransactionDuration": int(transaction["TransactionDuration"]),
            "LoginAttempts": int(transaction["LoginAttempts"]),
            "AccountBalance": float(transaction["AccountBalance"]),
            "TransactionType": transaction["TransactionType"],
            "Channel": transaction["Channel"],
            "CustomerOccupation": transaction["CustomerOccupation"],
        }
        try:
            resultat = requests.post(f"{API_ANOMALIES}/api/predict", json=entree, timeout=3).json()
        except (requests.RequestException, ValueError):
            return {"en_ligne": False, "lignes": []}


        compte = transaction["AccountID"]
        segment = clients.loc[compte, "segment"] if compte in clients.index else None
        lignes.append(
            {
                "compte": compte,
                "date": transaction["TransactionDate"].date(),
                "montant": round(transaction["TransactionAmount"]),
                "solde": round(transaction["AccountBalance"]),
                "canal": transaction["Channel"],
                "score": resultat.get("score_pct", 0),
                "seuil": round(float(resultat.get("seuil", 0)) * 100, 1),
                "alerte": bool(resultat.get("alerte")),
                "segment": SEGMENTS[segment]["nom"] if segment else "—",
            }
        )
    _ALERTES = {"en_ligne": True, "lignes": lignes}
    return _ALERTES


def etat_moteur() -> bool:
    try:
        return requests.get(f"{API_ANOMALIES}/api/health", timeout=1.5).ok
    except requests.RequestException:
        return False
