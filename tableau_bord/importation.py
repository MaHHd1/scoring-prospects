"""Lecture et normalisation d'un fichier de transactions fourni par la banque.

Le tableau de bord travaille sur six colonnes : compte, date, montant, sens,
solde, et quelques colonnes de contexte. Cette page accepte un CSV, TSV, TXT ou
JSON, laisse le conseiller associer les colonnes, puis écrit un fichier
normalisé que `donnees.chemin_transactions()` utilisera.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

IMPORTS = Path(__file__).resolve().parent / "imports"
EXTENSIONS = {".csv", ".tsv", ".txt", ".json"}
TAILLE_MAX = 30 * 1024 * 1024  # 30 Mo


class ErreurImport(Exception):
    """Fichier illisible ou colonnes inexploitables."""


# Colonnes attendues par le tableau de bord : (nom, libellé, obligatoire, mots-clés).
COLONNES = [
    ("AccountID", "Identifiant du compte", True, ["accountid", "compte", "clientid", "customerid", "numerocompte", "rib", "idclient"]),
    ("TransactionDate", "Date de la transaction", True, ["transactiondate", "date", "datetransaction", "dateoperation", "dateop", "datevaleur"]),
    ("TransactionAmount", "Montant", True, ["transactionamount", "montant", "amount", "valeur", "montanttransaction"]),
    ("TransactionType", "Sens (débit / crédit)", True, ["transactiontype", "type", "sens", "debitcredit", "natureoperation", "typeoperation"]),
    ("AccountBalance", "Solde du compte après opération", True, ["accountbalance", "solde", "balance", "soldecompte"]),
    ("Channel", "Canal (agence, guichet, en ligne…)", False, ["channel", "canal", "reseau", "support"]),
    ("CustomerOccupation", "Profession du client", False, ["customeroccupation", "profession", "metier", "occupation", "emploi"]),
    ("CustomerAge", "Âge du client", False, ["customerage", "age", "ageduclient"]),
    ("TransactionDuration", "Durée de l'opération (secondes)", False, ["transactionduration", "duree", "dureeoperation", "duration"]),
    ("LoginAttempts", "Tentatives de connexion", False, ["loginattempts", "tentatives", "tentativesconnexion"]),
    ("TransactionID", "Identifiant de la transaction", False, ["transactionid", "idtransaction", "id", "reference"]),
]


def _cle(nom: str) -> str:
    """« Numéro de compte » -> « numerodecompte » (sans accent ni ponctuation)."""
    sans_accent = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sans_accent.lower())


def _en_nombre(serie: pd.Series) -> pd.Series:
    """Convertit « 1 234,56 TND » ou « 1,234.56 » en nombres."""
    texte = serie.astype(str).str.replace("\u202f", "", regex=False).str.replace("\xa0", "", regex=False)
    texte = texte.str.replace(r"[^\d,.\-]", "", regex=True)
    virgule = texte.str.contains(",", regex=False)
    point = texte.str.contains(r"\.", regex=True)
    decimales_virgule = virgule & ~point
    milliers_virgule = virgule & point
    texte = texte.where(~decimales_virgule, texte.str.replace(",", ".", regex=False))
    texte = texte.where(~milliers_virgule, texte.str.replace(",", "", regex=False))
    return pd.to_numeric(texte, errors="coerce")


def _en_date(serie: pd.Series) -> pd.Series:
    echantillon = serie.dropna().astype(str).head(50)
    iso = echantillon.str.match(r"^\d{4}-\d{2}-\d{2}").mean() if len(echantillon) else 0
    return pd.to_datetime(serie, errors="coerce", dayfirst=iso < 0.6)


def lire(chemin: Path) -> pd.DataFrame:
    """Lit le fichier déposé et renvoie un tableau brut."""
    extension = chemin.suffix.lower()
    if extension not in EXTENSIONS:
        raise ErreurImport(
            f"Format « {extension or 'inconnu'} » non pris en charge. "
            "Déposez un CSV, TSV, TXT ou JSON (pour Excel : Fichier → Enregistrer sous → CSV)."
        )

    if extension == ".json":
        try:
            contenu = json.loads(chemin.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as erreur:
            raise ErreurImport(f"JSON illisible : {erreur}") from erreur
        if isinstance(contenu, dict):
            listes = [valeur for valeur in contenu.values() if isinstance(valeur, list)]
            if not listes:
                raise ErreurImport("Le JSON ne contient aucune liste d'opérations.")
            contenu = listes[0]
        if not isinstance(contenu, list) or not contenu or not isinstance(contenu[0], dict):
            raise ErreurImport("Le JSON doit contenir une liste d'objets (une opération par objet).")
        return pd.DataFrame(contenu)

    separateur = "\t" if extension == ".tsv" else None
    derniere_erreur: Exception | None = None
    for encodage in ("utf-8-sig", "latin-1"):
        try:
            if separateur is None:
                return pd.read_csv(chemin, encoding=encodage, sep=None, engine="python")
            return pd.read_csv(chemin, encoding=encodage, sep=separateur)
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as erreur:
            derniere_erreur = erreur
    raise ErreurImport(f"Fichier illisible : {derniere_erreur}")


def suggerer(colonnes: list[str]) -> dict[str, str]:
    """Associe chaque colonne attendue à la colonne du fichier qui lui ressemble."""
    disponibles = {_cle(colonne): colonne for colonne in colonnes}
    proposition: dict[str, str] = {}
    for nom, _libelle, _obligatoire, mots in COLONNES:
        proposition[nom] = ""
        for mot in mots:
            if mot in disponibles:
                proposition[nom] = disponibles[mot]
                break
        if proposition[nom]:
            continue
        for cle, origine in disponibles.items():
            if any(mot in cle for mot in mots):
                proposition[nom] = origine
                break
    return proposition


def apercu(tableau: pd.DataFrame, lignes: int = 6) -> dict:
    extrait = tableau.head(lignes).astype(str).where(tableau.head(lignes).notna(), "")
    return {
        "colonnes": [str(colonne) for colonne in tableau.columns],
        "lignes": extrait.values.tolist(),
        "nb_lignes": int(len(tableau)),
        "nb_colonnes": int(tableau.shape[1]),
    }


def normaliser(tableau: pd.DataFrame, correspondance: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """Renomme, nettoie et valide les colonnes ; renvoie le tableau et un rapport."""
    manquantes = [
        libelle
        for nom, libelle, obligatoire, _mots in COLONNES
        if obligatoire and not correspondance.get(nom)
    ]
    if manquantes:
        raise ErreurImport("Associez aussi : " + ", ".join(manquantes) + ".")

    renommage = {origine: nom for nom, origine in correspondance.items() if origine}
    if len(set(renommage)) != len(renommage):
        raise ErreurImport("Deux champs du tableau de bord pointent vers la même colonne.")
    donnees = tableau.rename(columns=renommage)

    donnees["TransactionDate"] = _en_date(donnees["TransactionDate"])
    donnees["TransactionAmount"] = _en_nombre(donnees["TransactionAmount"])
    donnees["AccountBalance"] = _en_nombre(donnees["AccountBalance"])

    sens = donnees["TransactionType"].astype(str).str.strip().str.lower()
    correspondance_sens = {
        "debit": "Debit", "débit": "Debit", "d": "Debit", "dr": "Debit",
        "retrait": "Debit", "withdrawal": "Debit", "payment": "Debit", "paiement": "Debit", "achat": "Debit",
        "credit": "Credit", "crédit": "Credit", "c": "Credit", "cr": "Credit",
        "deposit": "Credit", "dépôt": "Credit", "depot": "Credit", "versement": "Credit", "virement": "Credit",
    }
    donnees["TransactionType"] = sens.map(correspondance_sens)

    inconnus = sorted(set(sens[donnees["TransactionType"].isna()]))[:5]
    if inconnus:
        raise ErreurImport(
            "Sens non reconnus : " + ", ".join(inconnus)
            + ". Le fichier doit indiquer débit/crédit (ou debit/credit) dans cette colonne."
        )

    if "Channel" in donnees.columns:
        donnees["Channel"] = donnees["Channel"].astype(str).str.strip().replace({"": "Unknown", "nan": "Unknown"})
    else:
        donnees["Channel"] = "Unknown"

    if "CustomerOccupation" in donnees.columns:
        donnees["CustomerOccupation"] = (
            donnees["CustomerOccupation"].astype(str).str.strip().replace({"": "Unknown", "nan": "Unknown"})
        )
    else:
        donnees["CustomerOccupation"] = "Unknown"

    if "CustomerAge" in donnees.columns:
        donnees["CustomerAge"] = _en_nombre(donnees["CustomerAge"])
    else:
        donnees["CustomerAge"] = pd.Series([float("nan")] * len(donnees), index=donnees.index)

    if "TransactionID" not in donnees.columns:
        donnees["TransactionID"] = [f"TX{i:07d}" for i in range(1, len(donnees) + 1)]

    # Colonnes utiles au modèle d'anomalies : valeurs neutres si le fichier ne les fournit pas.
    for nom, defaut in (("TransactionDuration", 60), ("LoginAttempts", 1)):
        if nom in donnees.columns:
            donnees[nom] = _en_nombre(donnees[nom]).fillna(defaut)
        else:
            donnees[nom] = defaut

    donnees["AccountID"] = donnees["AccountID"].astype(str).str.strip()

    lignes_avant = len(donnees)
    donnees = donnees.dropna(subset=["TransactionDate", "TransactionAmount", "AccountBalance", "TransactionType"])
    donnees = donnees[donnees["AccountID"].ne("") & donnees["AccountID"].ne("nan")]
    donnees = donnees.sort_values("TransactionDate").reset_index(drop=True)

    if len(donnees) < 20:
        raise ErreurImport(
            f"Seules {len(donnees)} lignes exploitables : il en faut au moins 20 pour calculer des segments."
        )
    if donnees["AccountID"].nunique() < 5:
        raise ErreurImport("Moins de cinq comptes distincts : les quintiles RFM ne peuvent pas être calculés.")

    donnees["CustomerAge"] = donnees["CustomerAge"].fillna(
        donnees.groupby("AccountID")["CustomerAge"].transform("median")
    )
    donnees["CustomerAge"] = donnees["CustomerAge"].fillna(donnees["CustomerAge"].median()).fillna(40)

    colonnes = [
        "TransactionID", "AccountID", "TransactionDate", "TransactionAmount",
        "TransactionType", "AccountBalance", "Channel", "CustomerOccupation", "CustomerAge",
        "TransactionDuration", "LoginAttempts",
    ]
    donnees = donnees[colonnes]

    rapport = {
        "lignes_gardees": int(len(donnees)),
        "lignes_ignorees": int(lignes_avant - len(donnees)),
        "comptes": int(donnees["AccountID"].nunique()),
        "debut": donnees["TransactionDate"].min().date(),
        "fin": donnees["TransactionDate"].max().date(),
        "volume": float(donnees["TransactionAmount"].sum()),
    }
    return donnees, rapport


def enregistrer(donnees: pd.DataFrame) -> Path:
    """Écrit le tableau normalisé dans `imports/` et renvoie son chemin."""
    IMPORTS.mkdir(exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    chemin = IMPORTS / f"transactions_{horodatage}.csv"
    donnees.to_csv(chemin, index=False, date_format="%Y-%m-%d")
    return chemin
