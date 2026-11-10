"""Tableau de bord bancaire — vue d'ensemble du portefeuille clients.

Prototype destiné au conseiller : segments RFM, actions à mener et alertes
transactions. Port 5080 par défaut.
"""

from __future__ import annotations

import os

from flask import Flask, abort, jsonify, render_template

import donnees

app = Flask(__name__)


@app.template_filter("tnd")
def filtre_tnd(valeur: float) -> str:
    return f"{valeur:,.0f}".replace(",", " ") + " TND"


@app.template_filter("pct")
def filtre_pct(valeur: float) -> str:
    return f"{valeur * 100:.1f}".replace(".", ",") + " %"


@app.template_filter("virgule")
def filtre_virgule(valeur: float) -> str:
    return f"{float(valeur):.1f}".replace(".", ",")


@app.context_processor
def contexte_global():
    reference = donnees.date_reference()
    return {
        "banque": "Banque Atlas",
        "date_reference": reference.strftime("%d/%m/%Y"),
        "catalogue": donnees.SEGMENTS,
    }


@app.get("/")
def accueil():
    synthese = donnees.resume()
    alertes = donnees.alertes()
    details_reveiller = next(item for item in synthese["segments"] if item["cle"] == "a_reveiller")
    return render_template(
        "index.html",
        kpis=synthese["kpis"],
        segments=synthese["segments"],
        segment_a_reveiller=details_reveiller,
        alertes=alertes,
        a_reveiller=donnees.clients_du_segment("a_reveiller")[:6],
    )


@app.get("/segment/<cle>")
def segment(cle: str):
    if cle not in donnees.SEGMENTS:
        abort(404)
    synthese = donnees.resume()
    details = next(item for item in synthese["segments"] if item["cle"] == cle)
    return render_template(
        "segment.html",
        segment=details,
        clients=donnees.clients_du_segment(cle),
    )


@app.get("/api/sante")
def sante():
    return jsonify(
        {
            "statut": "ok",
            "site": "tableau de bord",
            "port": int(os.environ.get("PORT", 5080)),
            "moteur_alertes": {"en_ligne": donnees.etat_moteur()},
        }
    )


@app.errorhandler(404)
def page_absente(_erreur):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5080)),
        debug=False,
    )
