"""Données du tableau de bord bancaire : portefeuille, segments RFM et alertes.

Le tableau de bord ne remplace pas les API de modèles : il agrège le fichier de
transactions du projet (`api_isolation_forest/bank_transactions_data_2.csv`) pour
donner au conseiller une vue d'ensemble, et interroge l'API Isolation Forest
(port 5003) pour les transactions atypiques.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
FICHIER_TRANSACTIONS = BASE.parent / "api_isolation_forest" / "bank_transactions_data_2.csv"
IMPORTS = BASE / "imports"
ETAT = IMPORTS / "etat.json"
API_ANOMALIES = os.environ.get("API_ANOMALIES_URL", "http://127.0.0.1:5003")

SEUIL_INACTIF = 90  # jours sans transaction
NB_TRANSACTIONS_EXAMINEES = 6

# Modèles des autres membres du projet, exposés sur la fiche client.
MODELES = {
    "defaut": {
        "port": 5005,
        "nom": "Risque de défaut",
        "modele": "Gradient Boosting",
        "auteur": "Siwar Raouafi",
        "question": "Ce client risque-t-il de ne pas rembourser le mois prochain ?",
        "source": "Six mois d'historique reconstitués : factures = débits du mois, paiements = crédits du mois, retard = mois sans paiement.",
        "propose": True,
    },
    "segmentation": {
        "port": 5004,
        "nom": "Profil comportemental",
        "modele": "K-Means",
        "auteur": "Hedi Hassan",
        "question": "À quel profil de clientèle ce compte ressemble-t-il ?",
        "source": "Les 17 variables de carte sont projetées depuis les transactions : solde moyen, volume d'achats, retraits au distributeur, nombre d'opérations, ancienneté.",
        "propose": True,
    },
    "souscription": {
        "port": 5006,
        "nom": "Propension à souscrire",
        "modele": "LightGBM",
        "auteur": "Ranim Boujlel",
        "question": "Ce client est-il susceptible de souscrire un produit d'épargne ?",
        "source": "Âge, métier et solde viennent du compte ; situation familiale, logement et prêt restent à confirmer avec le client.",
        "propose": True,
    },
    "actifs": {
        "port": 5002,
        "nom": "Actifs bancaires estimés",
        "modele": "Lasso",
        "auteur": "Souha Mabrouk",
        "question": "Quelle valeur d'actifs bancaires estimer pour ce client ?",
        "source": "Simulateur : le modèle attend revenus et patrimoine, que la banque ne connaît pas dans ce jeu de données. Valeurs par défaut à ajuster.",
        "propose": False,
    },
    "revenu": {
        "port": 5001,
        "nom": "Potentiel de revenu élevé",
        "modele": "Random Forest",
        "auteur": "Mahdi Lakhoua",
        "question": "Ce client a-t-il un profil de revenu supérieur au seuil du modèle ?",
        "source": "Âge et profession viennent du compte ; le reste (études, situation familiale, heures travaillées) est au référentiel du modèle.",
        "propose": True,
    },
}
ORDRE_MODELES = ["defaut", "segmentation", "souscription", "actifs", "revenu"]

_JOURS_PAR_MOIS = 30.44

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


def _lire_etat() -> dict:
    """État du jeu de données choisi sur la page de démarrage."""
    try:
        return json.loads(ETAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def chemin_transactions() -> Path:
    """Fichier de transactions à utiliser : import de la banque, sinon exemple."""
    etat = _lire_etat()
    if etat.get("source") == "import":
        fichier = IMPORTS / str(etat.get("fichier", ""))
        if fichier.is_file():
            return fichier
    return FICHIER_TRANSACTIONS


def source_active() -> dict:
    """Décrit la source affichée dans le pied de page."""
    etat = _lire_etat()
    fichier = chemin_transactions()
    if fichier != FICHIER_TRANSACTIONS:
        return {
            "source": "import",
            "exemple": False,
            "libelle": etat.get("libelle") or fichier.name,
            "fichier": fichier.name,
            "le": etat.get("le", ""),
        }
    return {
        "source": "exemple",
        "exemple": True,
        "libelle": "Données d'exemple du projet",
        "fichier": FICHIER_TRANSACTIONS.name,
        "le": "",
    }


def jeu_choisi() -> bool:
    """Vrai dès que la page de démarrage a enregistré un choix (import ou exemple)."""
    return _lire_etat().get("source") in {"import", "exemple"}


def activer_exemple() -> None:
    IMPORTS.mkdir(exist_ok=True)
    ETAT.write_text(json.dumps({"source": "exemple"}, indent=2), encoding="utf-8")
    reinitialiser()


def reinitialiser() -> None:
    """Vide les caches pour que le prochain affichage relise le jeu actif."""
    global _ALERTES
    portefeuille.cache_clear()
    resume.cache_clear()
    clients_du_segment.cache_clear()
    _transactions.cache_clear()
    _ALERTES = None


def activer_import(fichier: Path, libelle: str) -> None:
    """Enregistre un import normalisé comme jeu de données actif."""
    IMPORTS.mkdir(exist_ok=True)
    ETAT.write_text(
        json.dumps(
            {
                "source": "import",
                "fichier": fichier.name,
                "libelle": libelle,
                "le": datetime.now().strftime("%d/%m/%Y à %H:%M"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    reinitialiser()


@lru_cache(maxsize=1)
def portefeuille() -> pd.DataFrame:
    """Une ligne par compte, avec les indicateurs RFM et le segment associé."""
    transactions = pd.read_csv(chemin_transactions(), parse_dates=["TransactionDate"])
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
    transactions = pd.read_csv(chemin_transactions(), parse_dates=["TransactionDate"])
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


@lru_cache(maxsize=1)
def _transactions() -> pd.DataFrame:
    return pd.read_csv(chemin_transactions(), parse_dates=["TransactionDate"])


def _mois_recents(compte: str, nombre: int = 6) -> list[dict]:
    """Volumes débit/crédit et retraits du compte, du mois le plus récent au plus ancien."""
    transactions = _transactions()
    transactions = transactions[transactions["AccountID"] == compte]
    reference = date_reference().to_period("M")
    mois = []
    for decalage in range(nombre):
        periode = reference - decalage
        du_mois = transactions[transactions["TransactionDate"].dt.to_period("M") == periode]
        debits = du_mois[du_mois["TransactionType"] == "Debit"]
        credits = du_mois[du_mois["TransactionType"] == "Credit"]
        retraits = debits[debits["Channel"] == "ATM"]
        mois.append(
            {
                "debits": float(debits["TransactionAmount"].sum()),
                "credits": float(credits["TransactionAmount"].sum()),
                "retraits": float(retraits["TransactionAmount"].sum()),
                "nb_debits": int(len(debits)),
                "nb_credits": int(len(credits)),
                "nb_retraits": int(len(retraits)),
                "nb_total": int(len(du_mois)),
            }
        )
    return mois


def _client(compte: str) -> dict | None:
    clients = portefeuille()
    if compte not in clients.index:
        return None
    fiche = _ligne_client(str(clients.loc[compte, "segment"]), compte, clients.loc[compte])
    transactions = _transactions()
    du_compte = transactions[transactions["AccountID"] == compte]
    fiche["premiere"] = du_compte["TransactionDate"].min().date()
    fiche["tenure"] = max(1, du_compte["TransactionDate"].dt.to_period("M").nunique())
    fiche["journalier"] = round(float(du_compte["TransactionAmount"].mean()))
    fiche["mois"] = _mois_recents(compte)
    return fiche


def fiche_client(compte: str) -> dict | None:
    return _client(compte)


def _arrondi(valeur: float) -> int:
    return int(round(valeur))


def valeurs_proposees(cle: str, compte: str) -> dict:
    """Valeurs placées dans le formulaire du modèle avant tout ajustement."""
    fiche = _client(compte)
    if fiche is None:
        return {}
    mois = fiche["mois"]
    if cle == "defaut":
        valeurs = {"LIMIT_BAL": max(1000, _arrondi(fiche["solde"] * 2))}
        for index in range(1, 7):
            donnees_mois = mois[index - 1]
            valeurs[f"BILL_AMT{index}"] = _arrondi(donnees_mois["debits"])
            nom_retard = "PAY_0" if index == 1 else f"PAY_{index}"
            valeurs[nom_retard] = 0 if donnees_mois["credits"] > 0 else 1
        for index in range(1, 5):
            valeurs[f"PAY_AMT{index}"] = _arrondi(mois[index - 1]["credits"])
        return valeurs

    if cle == "segmentation":
        total_debits = sum(item["debits"] for item in mois)
        total_credits = sum(item["credits"] for item in mois)
        total_retraits = sum(item["retraits"] for item in mois)
        nb_debits = sum(item["nb_debits"] for item in mois)
        nb_retraits = sum(item["nb_retraits"] for item in mois)
        mois_actifs = sum(1 for item in mois if item["nb_debits"] or item["credits"])
        return {
            "BALANCE": fiche["solde"],
            "BALANCE_FREQUENCY": 1.0,
            "PURCHASES": total_debits,
            "ONEOFF_PURCHASES": total_debits,
            "INSTALLMENTS_PURCHASES": 0.0,
            "CASH_ADVANCE": total_retraits,
            "PURCHASES_FREQUENCY": round(mois_actifs / fiche["tenure"], 2),
            "ONEOFF_PURCHASES_FREQUENCY": round(mois_actifs / fiche["tenure"], 2),
            "PURCHASES_INSTALLMENTS_FREQUENCY": 0.0,
            "CASH_ADVANCE_FREQUENCY": round(sum(1 for item in mois if item["nb_retraits"]) / fiche["tenure"], 2),
            "CASH_ADVANCE_TRX": nb_retraits,
            "PURCHASES_TRX": nb_debits,
            "CREDIT_LIMIT": max(fiche["solde"], fiche["volume"] / 2),
            "PAYMENTS": total_credits,
            "MINIMUM_PAYMENTS": round(fiche["solde"] * 0.05, 2),
            "PRC_FULL_PAYMENT": 1.0 if total_credits >= total_debits else 0.0,
            "TENURE": fiche["tenure"],
        }

    if cle == "souscription":
        metiers = {"Doctor": "management", "Engineer": "technician", "Retired": "retired", "Student": "student"}
        return {
            "age": fiche["age"],
            "job": metiers.get(fiche["occupation"], "unknown"),
            "balance": _arrondi(fiche["solde"]),
        }

    if cle == "revenu":
        professions = {
            "Doctor": "Prof-specialty",
            "Engineer": "Exec-managerial",
            "Retired": "Other-service",
            "Student": "Unknown",
        }
        return {
            "age": fiche["age"],
            "occupation": professions.get(fiche["occupation"], "Unknown"),
        }

    return {}


_INFOS_MODELES: dict[str, dict] = {}


def champs_modele(cle: str) -> list[dict]:
    """Champs attendus par l'API, lus depuis son /api/info (mis en cache)."""
    if cle not in _INFOS_MODELES:
        port = MODELES[cle]["port"]
        try:
            reponse = requests.get(f"http://127.0.0.1:{port}/api/info", timeout=3)
            reponse.raise_for_status()
            _INFOS_MODELES[cle] = reponse.json()
        except (requests.RequestException, ValueError):
            return []
    return _INFOS_MODELES[cle].get("champs", [])


def normaliser(cle: str, valeurs: dict) -> dict:
    """Convertit les valeurs d'un formulaire HTML vers les types attendus par l'API."""
    normalisees = {}
    for champ in champs_modele(cle):
        nom = champ["nom"]
        if nom not in valeurs:
            continue
        valeur = valeurs[nom]
        if champ.get("type") == "choix":
            options = champ.get("options", [])
            normalisees[nom] = valeur if valeur in options else champ.get("defaut")
            continue
        try:
            nombre = float(valeur)
        except (TypeError, ValueError):
            nombre = float(champ.get("defaut", 0))
        if champ.get("entier"):
            normalisees[nom] = int(round(nombre))
        else:
            normalisees[nom] = round(nombre, 2)
    return normalisees


def appeler_modele(cle: str, valeurs: dict) -> dict | None:
    port = MODELES[cle]["port"]
    try:
        reponse = requests.post(
            f"http://127.0.0.1:{port}/api/predict",
            json=normaliser(cle, valeurs),
            timeout=4,
        )
        reponse.raise_for_status()
        return reponse.json()
    except (requests.RequestException, ValueError):
        return None


# Verdicts écrits pour le conseiller, quand l'API ne renvoie qu'un libellé de cible.
VERDICTS = {
    "souscription": ("À proposer lors du prochain contact", "Peu réceptif pour l'instant"),
    "revenu": ("Profil au-dessus du seuil du modèle", "Sous le seuil du modèle"),
    "actifs": ("Valeur estimée par régression Lasso", "Valeur estimée par régression Lasso"),
}


def _presentation(cle: str, brut: dict) -> dict:
    """Traduit la réponse brute du modèle en éléments affichables."""
    seuil = brut.get("seuil")
    contacter = bool(brut.get("contacter"))

    if cle == "actifs":
        prediction = float(brut.get("prediction", 0))
        return {
            "valeur": f"{prediction:,.0f}".replace(",", " "),
            "unite": "unités du modèle",
            "jauge": None,
            "verdict": VERDICTS["actifs"][0],
            "ton": "neutre",
            "seuil": None,
        }

    pourcentage = brut.get("score_pct")
    if pourcentage is None:
        pourcentage = float(brut.get("score", 0)) * 100

    if cle in VERDICTS:
        verdict = VERDICTS[cle][0] if contacter else VERDICTS[cle][1]
    else:
        verdict = brut.get("cible", "")
        if cle == "segmentation" and seuil and float(pourcentage) < float(seuil) * 100:
            verdict += " · appartenance incertaine"

    return {
        "valeur": f"{pourcentage:.1f}".replace(".", ","),
        "unite": "%",
        "jauge": max(0.0, min(100.0, float(pourcentage))),
        "verdict": verdict,
        "ton": "alerte" if contacter else "neutre",
        "seuil": round(float(seuil) * 100, 1) if seuil else None,
    }


def scores_client(compte: str, remplacements: dict | None = None) -> list[dict]:
    """Exécute les cinq modèles sur un compte et renvoie de quoi les afficher."""
    remplacements = remplacements or {}
    modeles = []
    for cle in ORDRE_MODELES:
        definition = MODELES[cle]
        champs = champs_modele(cle)
        if not champs:
            modeles.append({**definition, "cle": cle, "en_ligne": False, "champs": [], "valeurs": {}, "resultat": None})
            continue

        valeurs = {champ["nom"]: champ.get("defaut") for champ in champs}
        valeurs.update(valeurs_proposees(cle, compte))
        valeurs_defaut = dict(valeurs)
        valeurs.update(normaliser(cle, remplacements.get(cle, {})))
        brut = appeler_modele(cle, valeurs)
        modeles.append(
            {
                **definition,
                "cle": cle,
                "en_ligne": brut is not None,
                "champs": [
            {
                **champ,
                "valeur": valeurs.get(champ["nom"]),
                "propose": valeurs_defaut.get(champ["nom"]),
            }
            for champ in champs
        ],
                "valeurs": valeurs,
                "resultat": _presentation(cle, brut) if brut else None,
            }
        )
    return modeles


def _entier(ligne, nom: str, defaut: int) -> int:
    """Valeur entière d'une ligne, avec repli si la colonne manque ou est vide."""
    try:
        return int(float(ligne.get(nom)))
    except (TypeError, ValueError):
        return defaut


def _transactions_a_examiner() -> pd.DataFrame:
    """Les transactions les plus déséquilibrées (montant / solde), une par compte."""
    transactions = pd.read_csv(chemin_transactions(), parse_dates=["TransactionDate"])
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
            "CustomerAge": _entier(transaction, "CustomerAge", 40),
            "TransactionDuration": _entier(transaction, "TransactionDuration", 60),
            "LoginAttempts": _entier(transaction, "LoginAttempts", 1),
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
