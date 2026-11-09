"""Espace client Banque Atlas — site commercial (prototype).

Pages :
  GET  /        page commerciale (offres, parcours, sécurité)
  GET  /offre   questionnaire client en deux écrans
  POST /offre   offre personnalisée (segment K-Means + règles commerciales)
  GET  /api/sante  état du site et du moteur (utilisé par lancer_tout.py)

Lancement :
    python app.py                  # http://127.0.0.1:5070
    PORT=5080 python app.py        # autre port
"""

import os
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import moteur

BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 5070))
BANQUE = os.environ.get("BANQUE", "Banque Atlas")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Présentation
# ---------------------------------------------------------------------------
@app.template_filter("tnd")
def filtre_tnd(valeur) -> str:
    """1800 -> « 1 800 TND » (espace fine insécable, comme en français)."""
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return str(valeur)
    return f"{nombre:,.0f}".replace(",", "\u202f") + " TND"


@app.template_filter("pct")
def filtre_pct(valeur) -> str:
    try:
        return f"{float(valeur):.0f} %"
    except (TypeError, ValueError):
        return "—"


@app.context_processor
def contexte_commun():
    return {"banque": BANQUE, "date": date.today().strftime("%d/%m/%Y")}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/")
def accueil():
    return render_template("index.html", cartes=list(moteur.CARTES.values()))


@app.get("/offre")
def formulaire():
    return render_template(
        "simulateur.html",
        etapes=moteur.etapes(),
        saisie=moteur.valeurs_defaut(),
        erreurs={},
    )


@app.post("/offre")
def offre():
    saisie = {nom: (request.form.get(nom) or "") for nom in moteur.CHAMPS}
    valeurs, erreurs = moteur.lire_formulaire(request.form)

    if erreurs:
        return (
            render_template(
                "simulateur.html",
                etapes=moteur.etapes(),
                saisie=saisie,
                erreurs=erreurs,
            ),
            400,
        )

    resultat = moteur.construire_offre(valeurs)
    return render_template(
        "resultat.html",
        offre=resultat,
        saisie=saisie,
    )


@app.get("/api/sante")
def sante():
    return jsonify(
        {
            "statut": "ok",
            "site": "espace client",
            "port": PORT,
            "moteur": moteur.etat_moteur(),
        }
    )


if __name__ == "__main__":
    print(f"Espace client {BANQUE} sur le port {PORT}", flush=True)
    app.run(host="127.0.0.1", port=PORT)
