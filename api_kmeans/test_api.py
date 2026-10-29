"""Vérifications de l'API (équivalent de la cellule VII.3 du guide d'équipe).

Les 4 vérifications doivent réussir :
  1. GET  /api/health   -> 200, statut "ok"
  2. GET  /api/info     -> 200, 17 champs avec libellés
  3. POST /api/predict  -> 200, score_pct / cible / seuil / contacter présents
  4. POST /api/predict  -> segments identiques au notebook
                           (C10001 -> 1, C10002 -> 2, C10003 -> 1)
En plus : fiche incomplète -> 400 avec la liste des erreurs.

Usage : python test_api.py     (API_URL=http://IP:PORT pour changer d'adresse)
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("API_URL", "http://127.0.0.1:5004").rstrip("/")

# Fiches brutes extraites du dataset (lignes du notebook)
FICHE_C10001 = {
    "BALANCE": 40.900749, "BALANCE_FREQUENCY": 0.818182, "PURCHASES": 95.40,
    "ONEOFF_PURCHASES": 0.00, "INSTALLMENTS_PURCHASES": 95.40, "CASH_ADVANCE": 0.0,
    "PURCHASES_FREQUENCY": 0.166667, "ONEOFF_PURCHASES_FREQUENCY": 0.0,
    "PURCHASES_INSTALLMENTS_FREQUENCY": 0.083333, "CASH_ADVANCE_FREQUENCY": 0.0,
    "CASH_ADVANCE_TRX": 0, "PURCHASES_TRX": 2, "CREDIT_LIMIT": 1000.0,
    "PAYMENTS": 201.802084, "MINIMUM_PAYMENTS": 139.509787,
    "PRC_FULL_PAYMENT": 0.0, "TENURE": 12,
}
FICHE_C10002 = {
    "BALANCE": 3202.467416, "BALANCE_FREQUENCY": 0.909091, "PURCHASES": 0.0,
    "ONEOFF_PURCHASES": 0.0, "INSTALLMENTS_PURCHASES": 0.0, "CASH_ADVANCE": 6442.945483,
    "PURCHASES_FREQUENCY": 0.0, "ONEOFF_PURCHASES_FREQUENCY": 0.0,
    "PURCHASES_INSTALLMENTS_FREQUENCY": 0.0, "CASH_ADVANCE_FREQUENCY": 0.25,
    "CASH_ADVANCE_TRX": 4, "PURCHASES_TRX": 0, "CREDIT_LIMIT": 7000.0,
    "PAYMENTS": 4103.032597, "MINIMUM_PAYMENTS": 1072.340217,
    "PRC_FULL_PAYMENT": 0.222222, "TENURE": 12,
}
FICHE_C10003 = {
    "BALANCE": 2495.148862, "BALANCE_FREQUENCY": 1.0, "PURCHASES": 773.17,
    "ONEOFF_PURCHASES": 773.17, "INSTALLMENTS_PURCHASES": 0.0, "CASH_ADVANCE": 0.0,
    "PURCHASES_FREQUENCY": 1.0, "ONEOFF_PURCHASES_FREQUENCY": 1.0,
    "PURCHASES_INSTALLMENTS_FREQUENCY": 0.0, "CASH_ADVANCE_FREQUENCY": 0.0,
    "CASH_ADVANCE_TRX": 0, "PURCHASES_TRX": 12, "CREDIT_LIMIT": 7500.0,
    "PAYMENTS": 622.066742, "MINIMUM_PAYMENTS": 627.284787,
    "PRC_FULL_PAYMENT": 0.0, "TENURE": 12,
}


def appel(path, corps=None):
    if corps is None:
        requete = urllib.request.Request(BASE + path)
    else:
        requete = urllib.request.Request(
            BASE + path,
            data=json.dumps(corps).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))
    except Exception as err:  # injoignable
        return None, {"erreurs": [type(err).__name__]}


resultats = []

# --- Vérification 1 : santé -------------------------------------------------
code, corps = appel("/api/health")
ok = code == 200 and corps.get("statut") == "ok"
resultats.append(("1. /api/health répond 200 et statut ok", ok, f"{code} {corps}"))

# --- Vérification 2 : info --------------------------------------------------
code, corps = appel("/api/info")
champs = corps.get("champs", [])
ok = (
    code == 200
    and len(champs) == 17
    and all(c.get("nom") and c.get("libelle") and c.get("type") == "nombre" for c in champs)
    and corps.get("nom")
    and corps.get("auteur")
    and corps.get("cible")
)
resultats.append(("2. /api/info : 17 champs avec libellés", bool(ok),
                  f"{len(champs)} champs, nom={corps.get('nom')!r}"))

# --- Vérification 3 : prédiction -------------------------------------------
code, corps = appel("/api/predict", FICHE_C10001)
attendus = {"score_pct", "cible", "seuil", "contacter"}
ok = code == 200 and attendus.issubset(corps) and isinstance(corps.get("contacter"), bool)
resultats.append(("3. /api/predict : score_pct/cible/seuil/contacter", ok, f"{code} {corps}"))

# --- Vérification 4 : segments identiques au notebook ----------------------
attendus_segments = [("C10001", FICHE_C10001, 1), ("C10002", FICHE_C10002, 2),
                     ("C10003", FICHE_C10003, 1)]
details, ok = [], True
for nom_client, fiche, segment_attendu in attendus_segments:
    code, corps = appel("/api/predict", fiche)
    obtenu = corps.get("segment")
    details.append(f"{nom_client}: attendu {segment_attendu}, obtenu {obtenu}")
    ok = ok and code == 200 and obtenu == segment_attendu
resultats.append(("4. Segments identiques au notebook", ok, " | ".join(details)))

# --- Bonus : fiche incomplète -> 400 ---------------------------------------
fiche_incomplete = dict(FICHE_C10001)
fiche_incomplete.pop("CREDIT_LIMIT")
code, corps = appel("/api/predict", fiche_incomplete)
ok = code == 400 and "erreurs" in corps
resultats.append(("5. Fiche incomplète -> 400 + erreurs", ok, f"{code} {corps}"))

# --- Bilan ------------------------------------------------------------------
print(f"API testée : {BASE}\n")
for libelle, ok, detail in resultats:
    print(f"[{'OK  ' if ok else 'ECHEC'}] {libelle}\n         {detail}")

echecs = sum(1 for _, ok, _ in resultats if not ok)
print(f"\n{len(resultats) - echecs}/{len(resultats)} vérifications réussies.")
sys.exit(1 if echecs else 0)
