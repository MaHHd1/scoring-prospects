"""Verifications de l'API (equivalent de la cellule VII.3 du guide d'equipe).

  1. GET  /api/health   -> 200, statut "ok"
  2. GET  /api/info     -> 200, 8 champs (5 nombres + 3 choix)
  3. POST /api/predict  -> 200, score_pct / cible / seuil / contacter presents
  4. Transaction extreme -> alerte ; transaction banale -> pas d'alerte
  5. Fiche incomplete / valeur invalide -> 400 avec la liste des erreurs

Usage : python test_api.py        (API_URL=http://IP:PORT pour changer d'adresse)
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("API_URL", "http://127.0.0.1:5003").rstrip("/")

BANALE = {"TransactionAmount": 120, "CustomerAge": 45, "TransactionDuration": 110,
          "LoginAttempts": 1, "AccountBalance": 5000,
          "TransactionType": "Debit", "Channel": "Branch", "CustomerOccupation": "Doctor"}
EXTREME = {"TransactionAmount": 1900, "CustomerAge": 20, "TransactionDuration": 20,
           "LoginAttempts": 5, "AccountBalance": 400,
           "TransactionType": "Debit", "Channel": "Online", "CustomerOccupation": "Student"}


def appel(path, corps=None):
    req = urllib.request.Request(BASE + path)
    if corps is not None:
        req = urllib.request.Request(BASE + path, data=json.dumps(corps).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def verifier(nom, condition, detail=""):
    print(("OK   " if condition else "ECHEC"), nom, detail)
    return condition


def main():
    res = []
    code, h = appel("/api/health")
    res.append(verifier("1. health", code == 200 and h.get("statut") == "ok"))

    code, i = appel("/api/info")
    types = [c["type"] for c in i.get("champs", [])]
    res.append(verifier("2. info", code == 200 and types.count("nombre") == 5 and types.count("choix") == 3, str(types)))

    code, b = appel("/api/predict", BANALE)
    res.append(verifier("3. predict (champs de sortie)", code == 200 and {"score_pct", "cible", "seuil", "contacter"} <= set(b), str(b)))

    code, e = appel("/api/predict", EXTREME)
    res.append(verifier("4. extreme > banale et alerte", code == 200 and e["score_pct"] > b["score_pct"] and e["contacter"] and not b["contacter"],
                        f"extreme={e.get('score_pct')} banale={b.get('score_pct')} seuil={b.get('seuil')}"))

    code, err = appel("/api/predict", {"TransactionAmount": 100})
    res.append(verifier("5a. fiche incomplete -> 400", code == 400 and "erreurs" in err))
    code, err = appel("/api/predict", {**BANALE, "Channel": "Fax"})
    res.append(verifier("5b. modalite inconnue -> 400", code == 400 and "erreurs" in err))

    print("\nTous les tests reussissent." if all(res) else "\nDes tests ont echoue.")
    sys.exit(0 if all(res) else 1)


if __name__ == "__main__":
    main()
