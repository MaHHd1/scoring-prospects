"""Moteur de l'offre de l'espace client (Banque Atlas).

Le client répond à un questionnaire court, en langage courant. Ce module :

1. traduit ses réponses en variables comportementales attendues par l'API K-Means
   (``api_kmeans``, port 5004) ;
2. interroge cette API pour obtenir le segment de clientèle ;
3. applique les règles commerciales de la banque (carte recommandée, plafond,
   arguments, synthèse pour le conseiller).

Les hypothèses de traduction sont regroupées dans les constantes ci-dessous afin
d'être relues et ajustées facilement (elles sont aussi listées dans README.md).
"""

from __future__ import annotations

import os

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
URL_API = os.environ.get("API_KMEANS_URL", "http://127.0.0.1:5004").rstrip("/")
DELAI_API = float(os.environ.get("API_KMEANS_DELAI", "3"))

# Retrait moyen au distributeur, utilisé pour déduire un nombre de retraits
# annuels à partir du montant retiré chaque mois.
RETRAIT_MOYEN_TND = 80.0

# Le modèle a été entraîné sur 30 paiements par mois au maximum et 123 avances.
PURCHASES_TRX_MAX = 358
CASH_ADVANCE_TRX_MAX = 123
TENURE_MIN, TENURE_MAX = 6, 12

# Répartition "achats en une fois" / "achats échelonnés" selon la préférence de
# paiement déclarée.
RATIOS_PAIEMENT = {
    "unique": (0.85, 0.15),
    "echelonne": (0.20, 0.80),
    "mixte": (0.50, 0.50),
}

# Part du solde remboursée chaque mois (PRC_FULL_PAYMENT) et part des dépenses
# effectivement payée (PAYMENTS).
PRC_FULL_PAYMENT = {"total": 1.0, "partiel": 0.4, "minimum": 0.0}
PART_PAYEE = {"total": 1.0, "partiel": 0.6, "minimum": 0.25}

# ---------------------------------------------------------------------------
# Questionnaire client
# ---------------------------------------------------------------------------
CHAMPS = {
    "revenu_mensuel": {
        "libelle": "Revenu net mensuel du foyer",
        "type": "nombre",
        "min": 300,
        "max": 30000,
        "pas": 50,
        "defaut": 1800,
        "unite": "TND",
        "aide": "Après impôts. Sert uniquement à vérifier que le plafond reste raisonnable.",
    },
    "anciennete": {
        "libelle": "Depuis combien d'années utilisez-vous une carte ?",
        "type": "nombre",
        "min": 0,
        "max": 40,
        "pas": 1,
        "defaut": 3,
        "unite": "ans",
        "aide": "0 si c'est votre première carte.",
    },
    "limite_actuelle": {
        "libelle": "Plafond de votre carte actuelle",
        "type": "nombre",
        "min": 0,
        "max": 30000,
        "pas": 100,
        "defaut": 3000,
        "unite": "TND",
        "aide": "0 si vous n'avez pas encore de carte.",
    },
    "depenses_mensuelles": {
        "libelle": "Dépenses payées par carte, par mois",
        "type": "nombre",
        "min": 0,
        "max": 4000,
        "pas": 10,
        "defaut": 450,
        "unite": "TND",
        "aide": "Courses, essence, abonnements, achats en ligne…",
    },
    "paiement": {
        "libelle": "Comment réglez-vous vos achats ?",
        "type": "choix",
        "defaut": "mixte",
        "options": [
            {"valeur": "unique", "libelle": "En une seule fois"},
            {"valeur": "echelonne", "libelle": "En plusieurs fois (3x, 6x…)"},
            {"valeur": "mixte", "libelle": "Les deux selon les achats"},
        ],
    },
    "frequence": {
        "libelle": "Nombre de paiements par carte, par mois",
        "type": "nombre",
        "min": 0,
        "max": 60,
        "pas": 1,
        "defaut": 8,
        "unite": "paiements",
        "aide": "Un paiement = un passage en caisse ou un achat en ligne.",
    },
    "retraits_mensuels": {
        "libelle": "Retraits d'espèces, par mois",
        "type": "nombre",
        "min": 0,
        "max": 3900,
        "pas": 10,
        "defaut": 0,
        "unite": "TND",
        "aide": "0 si vous ne retirez jamais d'espèces.",
    },
    "solde_moyen": {
        "libelle": "Solde moyen de votre compte courant",
        "type": "nombre",
        "min": 0,
        "max": 19000,
        "pas": 50,
        "defaut": 900,
        "unite": "TND",
        "aide": "Ordre de grandeur, pas le solde du jour.",
    },
    "remboursement": {
        "libelle": "Comment remboursez-vous votre carte ?",
        "type": "choix",
        "defaut": "partiel",
        "options": [
            {"valeur": "total", "libelle": "Je rembourse la totalité chaque mois"},
            {"valeur": "partiel", "libelle": "Je rembourse une partie"},
            {"valeur": "minimum", "libelle": "Je paie le minimum"},
        ],
    },
}

# Le questionnaire est découpé en deux écrans.
ETAPES_DEFINITION = [
    ("Votre profil", ["revenu_mensuel", "anciennete", "limite_actuelle"]),
    ("Votre usage de la carte", [
        "depenses_mensuelles", "paiement", "frequence",
        "retraits_mensuels", "solde_moyen", "remboursement",
    ]),
]

# ---------------------------------------------------------------------------
# Offres commerciales et règles bancaires
# ---------------------------------------------------------------------------
CARTES = {
    "essentielle": {
        "cle": "essentielle",
        "nom": "Atlas Essentielle",
        "accroche": "La carte du quotidien, sans cotisation.",
        "cotisation": "Gratuite",
        "cashback": "0,5 %",
        "plafond_min": 1000,
        "plafond_max": 5000,
        "avantages": [
            "Paiements et retraits en Tunisie et à l'étranger",
            "Notification à chaque paiement",
            "Assurance achat 90 jours",
        ],
    },
    "gold": {
        "cle": "gold",
        "nom": "Atlas Gold",
        "accroche": "Plus de marge, sans compromis.",
        "cotisation": "120 TND/an",
        "cashback": "1 %",
        "plafond_min": 5000,
        "plafond_max": 15000,
        "avantages": [
            "Retraits sans frais jusqu'à 1 000 TND/mois",
            "Paiement en 3x sans frais dès 300 TND",
            "Assurance voyage et bagages",
            "Ligne prioritaire en agence",
        ],
    },
    "infinite": {
        "cle": "infinite",
        "nom": "Atlas Infinite",
        "accroche": "L'excellence, au quotidien.",
        "cotisation": "400 TND/an",
        "cashback": "2 %",
        "plafond_min": 15000,
        "plafond_max": 40000,
        "avantages": [
            "Plafond élevé et adaptable chaque mois",
            "Accès aux salons d'aéroport (4 passages/an)",
            "Conciergerie 24/7 et assurance voyage premium",
            "Conseiller dédié",
        ],
    },
}

# Segment K-Means -> carte recommandée.
SEGMENT_VERS_CARTE = {0: "infinite", 1: "essentielle", 2: "gold"}

# Libellés client des segments du modèle.
PROFILS = {
    0: {
        "nom": "Achats élevés",
        "resume": "vous utilisez votre carte de façon intensive et régulière",
    },
    1: {
        "nom": "Profil équilibré",
        "resume": "votre usage de la carte est modéré et régulier",
    },
    2: {
        "nom": "Trésorerie",
        "resume": "les retraits d'espèces occupent une place importante dans votre usage",
    },
}

# Multiple du revenu net utilisé comme plafond d'endettement de la banque.
MULTIPLE_REVENU = 3

# Paliers de cartes, du moins cher au plus cher (utilisé pour rétrograder une offre
# dont le plafond minimal dépasse la capacité de remboursement du client).
ORDRE_CARTES = ["essentielle", "gold", "infinite"]
# Multiple des dépenses mensuelles servant de base au plafond recommandé.
MULTIPLE_DEPENSES = {"essentielle": 2.0, "gold": 2.5, "infinite": 3.0}


def etapes() -> list[dict]:
    """Questionnaire prêt à afficher : écrans et champs dans l'ordre."""
    return [
        {"titre": titre, "champs": [(nom, CHAMPS[nom]) for nom in noms]}
        for titre, noms in ETAPES_DEFINITION
    ]


def valeurs_defaut() -> dict:
    """Valeurs initiales du formulaire (chaînes, comme un formulaire HTML)."""
    return {
        nom: str(champ["defaut"])
        for nom, champ in CHAMPS.items()
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def lire_formulaire(donnees) -> tuple[dict, dict]:
    """Valide les réponses du client.

    Retourne ``(valeurs, erreurs)`` : ``valeurs`` ne contient que les champs
    valides (nombres convertis en float, choix en chaîne) et ``erreurs`` associe
    un message à chaque champ refusé.
    """
    valeurs, erreurs = {}, {}

    for nom, champ in CHAMPS.items():
        brut = (donnees.get(nom) or "").strip()

        if champ["type"] == "choix":
            autorisees = {option["valeur"] for option in champ["options"]}
            if brut not in autorisees:
                erreurs[nom] = "Choisissez une option."
            else:
                valeurs[nom] = brut
            continue

        if brut == "":
            erreurs[nom] = "Ce champ est obligatoire."
            continue

        try:
            valeur = float(brut.replace(" ", "").replace(",", "."))
        except ValueError:
            erreurs[nom] = "Indiquez un nombre."
            continue

        if valeur < champ["min"] or valeur > champ["max"]:
            erreurs[nom] = (
                f"Indiquez une valeur entre {champ['min']:.0f} et {champ['max']:.0f}"
                f" {champ['unite']}."
            )
            continue

        valeurs[nom] = valeur

    return valeurs, erreurs


# ---------------------------------------------------------------------------
# Traduction des réponses en variables du modèle
# ---------------------------------------------------------------------------
def variables_modele(valeurs: dict) -> dict:
    """Construit les 17 variables attendues par l'API K-Means.

    Chaque variable est une grandeur annuelle (le modèle a été entraîné sur des
    montants annuels) obtenue à partir des réponses mensuelles du client.
    """
    ratio_unique, ratio_echelonne = RATIOS_PAIEMENT[valeurs["paiement"]]

    achats_an = valeurs["depenses_mensuelles"] * 12
    retraits_an = valeurs["retraits_mensuels"] * 12

    # Fréquence d'achat : proportion des 30 jours du mois où la carte sert.
    frequence_achat = min(1.0, valeurs["frequence"] / 30)
    nb_paiements = min(PURCHASES_TRX_MAX, round(valeurs["frequence"] * 12))

    # Nombre de retraits annuels déduit du montant retiré chaque mois.
    retraits_par_mois = (
        round(valeurs["retraits_mensuels"] / RETRAIT_MOYEN_TND)
        if valeurs["retraits_mensuels"] > 0 else 0
    )
    nb_avances = min(CASH_ADVANCE_TRX_MAX, retraits_par_mois * 12)

    paiements = (achats_an + retraits_an) * PART_PAYEE[valeurs["remboursement"]]

    return {
        "BALANCE": valeurs["solde_moyen"],
        "BALANCE_FREQUENCY": 0.9 if valeurs["solde_moyen"] > 0 else 0.3,
        "PURCHASES": achats_an,
        "ONEOFF_PURCHASES": achats_an * ratio_unique,
        "INSTALLMENTS_PURCHASES": achats_an * ratio_echelonne,
        "CASH_ADVANCE": retraits_an,
        "PURCHASES_FREQUENCY": frequence_achat,
        "ONEOFF_PURCHASES_FREQUENCY": frequence_achat * ratio_unique,
        "PURCHASES_INSTALLMENTS_FREQUENCY": frequence_achat * ratio_echelonne,
        "CASH_ADVANCE_FREQUENCY": min(1.5, nb_avances / 12),
        "CASH_ADVANCE_TRX": nb_avances,
        "PURCHASES_TRX": nb_paiements,
        "CREDIT_LIMIT": max(50.0, valeurs["limite_actuelle"]),
        "PAYMENTS": paiements,
        "MINIMUM_PAYMENTS": max(0.02, paiements * 0.10),
        "PRC_FULL_PAYMENT": PRC_FULL_PAYMENT[valeurs["remboursement"]],
        "TENURE": min(TENURE_MAX, max(TENURE_MIN, round(valeurs["anciennete"] * 12))),
    }


def segment_estime(valeurs: dict) -> int:
    """Segmentation de secours, utilisée UNIQUEMENT si l'API est injoignable.

    Approximation volontairement simple, annoncée comme indicative sur la page
    de résultat : elle ne remplace pas le modèle K-Means.
    """
    depenses = valeurs["depenses_mensuelles"]
    retraits = valeurs["retraits_mensuels"]
    total = depenses + retraits

    if total > 0 and retraits / total >= 0.35:
        return 2
    if depenses >= 600 or (valeurs["paiement"] == "unique" and depenses >= 400):
        return 0
    return 1


# ---------------------------------------------------------------------------
# Appel de l'API de segmentation
# ---------------------------------------------------------------------------
def appeler_api(variables: dict) -> dict | None:
    """Renvoie ``{"segment", "score", "cible"}`` ou ``None`` si l'API ne répond pas."""
    try:
        reponse = requests.post(
            f"{URL_API}/api/predict", json=variables, timeout=DELAI_API
        )
        if reponse.status_code != 200:
            return None
        donnees = reponse.json()
        segment = int(donnees["segment"])
        if segment not in PROFILS:
            return None
        return {
            "segment": segment,
            "score": round(float(donnees.get("score_pct", 0.0)), 1),
            "api": True,
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def etat_moteur() -> dict:
    """État de l'API de segmentation, pour /api/sante (délai court)."""
    try:
        reponse = requests.get(f"{URL_API}/api/health", timeout=min(DELAI_API, 1.5))
        return {"en_ligne": reponse.status_code == 200}
    except requests.RequestException:
        return {"en_ligne": False}


# ---------------------------------------------------------------------------
# Règles commerciales
# ---------------------------------------------------------------------------
def carte_recommandee(segment: int, valeurs: dict) -> tuple[dict, bool]:
    """Carte du segment, ramenée à un palier finançable.

    Le modèle regroupe parfois des clients très différents dans un même segment.
    Si le plafond minimal de la carte du segment dépasse trois mois de revenu net,
    on redescend d'un palier : la banque ne propose pas une carte que le client ne
    peut pas rembourser. Le second élément indique si l'offre a été ajustée.
    """
    cle = SEGMENT_VERS_CARTE[segment]
    plafond_revenu = valeurs["revenu_mensuel"] * MULTIPLE_REVENU
    ajustee = False

    while cle != ORDRE_CARTES[0] and CARTES[cle]["plafond_min"] > plafond_revenu:
        cle = ORDRE_CARTES[ORDRE_CARTES.index(cle) - 1]
        ajustee = True

    return CARTES[cle], ajustee


def calculer_plafond(carte: dict, valeurs: dict) -> int:
    """Plafond recommandé, arrondi aux 100 TND.

    Règle : ``min(dépenses × multiple de la carte, plafond de la carte,
    3 mois de revenu net)``, sans descendre sous le plancher de la carte quand
    le revenu le permet.
    """
    base = valeurs["depenses_mensuelles"] * MULTIPLE_DEPENSES[carte["cle"]]
    plafond_revenu = valeurs["revenu_mensuel"] * MULTIPLE_REVENU

    plafond = min(base, carte["plafond_max"], plafond_revenu)
    plafond = max(plafond, min(carte["plafond_min"], plafond_revenu))
    return int(round(plafond / 100) * 100)


def construire_offre(valeurs: dict) -> dict:
    """Offre complète : carte, plafond, arguments et synthèse conseiller."""
    variables = variables_modele(valeurs)
    resultat_api = appeler_api(variables)

    if resultat_api is None:
        segment = segment_estime(valeurs)
        pertinence = None
        degrade = True
    else:
        segment = resultat_api["segment"]
        pertinence = resultat_api["score"]
        degrade = False

    profil = PROFILS[segment]
    carte, ajustee = carte_recommandee(segment, valeurs)
    plafond = calculer_plafond(carte, valeurs)

    return {
        "carte": carte,
        "plafond": plafond,
        "segment": segment,
        "profil": profil,
        "pertinence": pertinence,
        "degrade": degrade,
        "ajustee": ajustee,
        "raisons": _raisons(valeurs, segment, profil, carte, plafond, ajustee),
        "conseiller": _synthese_conseiller(valeurs, segment, carte, plafond, pertinence, degrade),
        "valeurs": valeurs,
        "variables": variables,
    }


def _raisons(valeurs, segment, profil, carte, plafond, ajustee=False) -> list[str]:
    """Arguments commerciaux, dans le vocabulaire du client."""
    depenses = f"{valeurs['depenses_mensuelles']:.0f} TND"
    retraits = f"{valeurs['retraits_mensuels']:.0f} TND"
    frequence = f"{valeurs['frequence']:.0f} paiements par mois"

    if segment == 0 and ajustee:
        premier = (
            f"Vous payez environ {depenses} par mois avec {frequence} : votre profil "
            f"« {profil['nom']} » est actif, mais votre revenu net ne permet pas encore "
            "une carte à plafond élevé."
        )
    elif segment == 0:
        premier = (
            f"Vous payez environ {depenses} par mois avec {frequence} : votre profil "
            f"« {profil['nom']} » demande un plafond élevé et des avantages sur vos achats."
        )
    elif segment == 2:
        premier = (
            f"Vos retraits d'espèces ({retraits} par mois) pèsent lourd dans votre usage : "
            f"votre profil « {profil['nom']} » appelle une carte avec retraits sans frais "
            "et un suivi de trésorerie."
        )
    else:
        premier = (
            f"Vos dépenses de carte ({depenses} par mois) restent modérées : votre profil "
            f"« {profil['nom']} » n'a pas besoin d'une cotisation élevée."
        )

    raisons = [premier]

    if ajustee:
        raisons.append(
            "Carte ajustée à votre capacité de remboursement : le plafond minimal de la "
            "carte de votre segment dépasse trois mois de votre revenu net."
        )

    raisons.append(
        f"Plafond recommandé de {plafond} TND : environ "
        f"{MULTIPLE_DEPENSES[carte['cle']]:.1f} mois de vos dépenses, plafonné à "
        f"{MULTIPLE_REVENU} mois de revenu net."
    )

    if valeurs["remboursement"] == "total":
        raisons.append(
            "Vous remboursez la totalité chaque mois : aucune dépense d'intérêts, et la "
            "cotisation de la première année est offerte."
        )
    elif valeurs["remboursement"] == "partiel":
        raisons.append(
            "Votre remboursement partiel est compatible avec nos échéanciers sans frais "
            "dès 300 TND d'achat."
        )
    else:
        raisons.append(
            "Vous payez le minimum : des intérêts s'appliquent. Votre conseiller peut vous "
            "proposer un étalement à taux réduit."
        )

    if valeurs["retraits_mensuels"] > 0:
        raisons.append(
            f"Vos retraits ({retraits} par mois) restent dans la franchise de "
            f"{carte['nom']}."
        )

    return raisons


def _synthese_conseiller(valeurs, segment, carte, plafond, pertinence, degrade) -> dict:
    """Résumé prêt à l'emploi pour le conseiller en agence."""
    prioritaire = segment == 0 and not degrade

    if degrade:
        action = "Reprendre la simulation dès que le moteur est disponible"
    elif prioritaire:
        action = "Recontacter sous 48 h"
    elif segment == 2:
        action = "Rendez-vous conseiller : accompagnement trésorerie"
    else:
        action = "Envoyer la documentation et confirmer en agence"

    return {
        "segment": f"Segment {segment} · {PROFILS[segment]['nom']}",
        "profil": PROFILS[segment]["resume"],
        "pertinence": pertinence,
        "prioritaire": prioritaire,
        "action": action,
        "carte": carte["nom"],
        "plafond": plafond,
        "resume": [
            ("Revenu net mensuel", f"{valeurs['revenu_mensuel']:.0f} TND"),
            ("Dépenses carte / mois", f"{valeurs['depenses_mensuelles']:.0f} TND"),
            ("Retraits / mois", f"{valeurs['retraits_mensuels']:.0f} TND"),
            ("Paiements / mois", f"{valeurs['frequence']:.0f}"),
            ("Ancienneté carte", f"{valeurs['anciennete']:.0f} an(s)"),
        ],
        "note": (
            "Segment calculé par le modèle K-Means de la banque (17 variables "
            "comportementales). Le score de pertinence mesure la confiance "
            "d'appartenance au segment."
        ),
    }
