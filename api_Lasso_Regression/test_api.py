"""Vérifications de l'API Lasso Regression (équivalent des tests des autres modèles).

Vérifications :
  1. GET  /api/health   -> 200, statut "ok", fichier_modele_present True
  2. GET  /api/info     -> 200, 5 champs avec libellés et bornes, métriques de validation croisée
  3. POST /api/predict  -> 200, prediction numérique renvoyée
  4. POST /api/predict  -> 400, rejet de valeurs négatives
  5. POST /api/predict  -> 400, rejet de champs manquants

Usage : python test_api.py     (PORT=5002 ou API_URL=http://127.0.0.1:5002)
"""

import json
import os
import sys
import urllib.error
import urllib.request

PORT = os.environ.get("PORT", "5002")
BASE = os.environ.get("API_URL", f"http://127.0.0.1:{PORT}").rstrip("/")

FICHE_TEST = {
    "income_annum": 5000000,
    "luxury_assets_value": 5000000,
    "loan_amount": 5000000,
    "commercial_assets_value": 3000000,
    "residential_assets_value": 3000000,
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
    except Exception as err:
        return None, {"erreurs": [type(err).__name__]}


def main():
    resultats = []

    # 1. Santé
    code, corps = appel("/api/health")
    ok = code == 200 and corps.get("statut") == "ok" and corps.get("fichier_modele_present") is True
    resultats.append(("1. /api/health répond 200 et statut ok", ok, f"{code} {corps}"))

    # 2. Info
    code, corps = appel("/api/info")
    champs = corps.get("champs", [])
    ok = (
        code == 200
        and len(champs) == 5
        and all(c.get("nom") and c.get("libelle") and c.get("type") == "nombre" for c in champs)
        and corps.get("nom") == "Lasso Regression"
        and "metriques_validation_croisee" in corps
    )
    resultats.append(("2. /api/info : 5 champs avec libellés et métriques", bool(ok),
                      f"{len(champs)} champs, nom={corps.get('nom')!r}"))

    # 3. Prédiction nominale
    code, corps = appel("/api/predict", FICHE_TEST)
    ok = (
        code == 200
        and "prediction" in corps
        and isinstance(corps["prediction"], (int, float))
        and corps["prediction"] > 0
    )
    resultats.append(("3. /api/predict : prédiction d'actif valide", ok, f"{code} {corps}"))

    # 4. Valeur négative -> 400
    fiche_negative = dict(FICHE_TEST, income_annum=-100)
    code, corps = appel("/api/predict", fiche_negative)
    ok = code == 400 and "erreurs" in corps
    resultats.append(("4. Valeur négative rejetée (400)", ok, f"{code} {corps}"))

    # 5. Champ manquant -> 400
    fiche_manquante = dict(FICHE_TEST)
    fiche_manquante.pop("loan_amount")
    code, corps = appel("/api/predict", fiche_manquante)
    ok = code == 400 and "erreurs" in corps
    resultats.append(("5. Fiche incomplète rejetée (400)", ok, f"{code} {corps}"))

    print(f"API testée : {BASE}\n")
    for libelle, ok_val, detail in resultats:
        print(f"[{'OK  ' if ok_val else 'ECHEC'}] {libelle}\n         {detail}")

    echecs = sum(1 for _, ok_val, _ in resultats if not ok_val)
    print(f"\n{len(resultats) - echecs}/{len(resultats)} vérifications réussies.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
