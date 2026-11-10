"""Tableau de bord bancaire — vue d'ensemble du portefeuille clients.

Prototype destiné au conseiller : page de démarrage (import du fichier de la
banque), segments RFM, actions à mener et alertes transactions. Port 5080.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

import donnees
import importation

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = importation.TAILLE_MAX

# Pages accessibles avant d'avoir choisi un jeu de données.
SANS_GARDE = {"static", "demarrer", "demarrer_analyser", "demarrer_activer", "demarrer_exemple", "sante"}


@app.template_filter("tnd")
def filtre_tnd(valeur: float) -> str:
    return f"{valeur:,.0f}".replace(",", " ") + " TND"


@app.template_filter("pct")
def filtre_pct(valeur: float) -> str:
    return f"{valeur * 100:.1f}".replace(".", ",") + " %"


@app.template_filter("virgule")
def filtre_virgule(valeur: float) -> str:
    return f"{float(valeur):.1f}".replace(".", ",")


@app.before_request
def exiger_demarrage():
    """Tant que le conseiller n'a pas choisi ses données, seule la page de démarrage répond."""
    if request.endpoint in SANS_GARDE or request.path.startswith("/static/"):
        return None
    if not donnees.jeu_choisi():
        return redirect(url_for("demarrer"))
    return None


@app.context_processor
def contexte_global():
    source = donnees.source_active()
    reference = donnees.date_reference() if donnees.jeu_choisi() else None
    return {
        "banque": "Banque Atlas",
        "date_reference": reference.strftime("%d/%m/%Y") if reference else "",
        "catalogue": donnees.SEGMENTS,
        "source": source,
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


@app.get("/client/<compte>")
def client(compte: str):
    fiche = donnees.fiche_client(compte)
    if fiche is None:
        abort(404)
    return render_template(
        "fiche.html",
        client=fiche,
        modeles=donnees.scores_client(compte),
    )


@app.post("/client/<compte>")
def client_recalcul(compte: str):
    fiche = donnees.fiche_client(compte)
    if fiche is None:
        abort(404)
    cle = request.form.get("modele")
    if cle not in donnees.MODELES:
        abort(400)
    # « Recalculer » envoie les valeurs saisies, « Réinitialiser » les ignore :
    # la fiche est alors rendue avec les valeurs proposées pour ce client.
    valeurs = {}
    if request.form.get("action") != "reinitialiser":
        valeurs = {nom: valeur for nom, valeur in request.form.items() if nom not in {"modele", "action"}}
    return render_template(
        "fiche.html",
        client=fiche,
        modeles=donnees.scores_client(compte, remplacements={cle: valeurs}),
    )


# ----------------------------- page de démarrage -----------------------------


@app.get("/demarrer")
def demarrer():
    return render_template(
        "demarrer.html",
        etape="fichier",
        source=donnees.source_active(),
        extensions=sorted(importation.EXTENSIONS),
        taille_max=importation.TAILLE_MAX // (1024 * 1024),
    )


def _page_colonnes(chemin: Path, nom_origine: str, erreur: str | None = None, correspondance=None):
    try:
        tableau = importation.lire(chemin)
    except importation.ErreurImport as probleme:
        return render_template(
            "demarrer.html",
            etape="fichier",
            source=donnees.source_active(),
            erreur=str(probleme),
            extensions=sorted(importation.EXTENSIONS),
            taille_max=importation.TAILLE_MAX // (1024 * 1024),
        )

    colonnes = [str(colonne) for colonne in tableau.columns]
    return render_template(
        "demarrer.html",
        etape="colonnes",
        source=donnees.source_active(),
        fichier=chemin.name,
        nom_origine=nom_origine,
        apercu=importation.apercu(tableau),
        colonnes=colonnes,
        champs=importation.COLONNES,
        correspondance=correspondance or importation.suggerer(colonnes),
        erreur=erreur,
        extensions=sorted(importation.EXTENSIONS),
        taille_max=importation.TAILLE_MAX // (1024 * 1024),
    )


@app.post("/demarrer/analyser")
def demarrer_analyser():
    fichier = request.files.get("fichier")
    if fichier is None or not fichier.filename:
        return render_template(
            "demarrer.html",
            etape="fichier",
            source=donnees.source_active(),
            erreur="Choisissez un fichier à importer.",
            extensions=sorted(importation.EXTENSIONS),
            taille_max=importation.TAILLE_MAX // (1024 * 1024),
        )

    nom_origine = Path(fichier.filename).name
    extension = Path(nom_origine).suffix.lower()
    if extension not in importation.EXTENSIONS:
        return render_template(
            "demarrer.html",
            etape="fichier",
            source=donnees.source_active(),
            erreur=(
                f"Format « {extension or 'inconnu'} » non pris en charge. "
                "Utilisez un CSV, TSV, TXT ou JSON — pour Excel, enregistrez d'abord en CSV."
            ),
            extensions=sorted(importation.EXTENSIONS),
            taille_max=importation.TAILLE_MAX // (1024 * 1024),
        )

    importation.IMPORTS.mkdir(exist_ok=True)
    for ancien in importation.IMPORTS.glob("tmp_*"):
        try:
            ancien.unlink()
        except OSError:
            pass
    chemin = importation.IMPORTS / f"tmp_{uuid.uuid4().hex[:10]}{extension}"
    fichier.save(chemin)
    if chemin.stat().st_size > importation.TAILLE_MAX:
        chemin.unlink(missing_ok=True)
        return render_template(
            "demarrer.html",
            etape="fichier",
            source=donnees.source_active(),
            erreur=f"Fichier trop volumineux (maximum {importation.TAILLE_MAX // (1024 * 1024)} Mo).",
            extensions=sorted(importation.EXTENSIONS),
            taille_max=importation.TAILLE_MAX // (1024 * 1024),
        )
    return _page_colonnes(chemin, nom_origine)


@app.post("/demarrer/activer")
def demarrer_activer():
    nom = Path(request.form.get("fichier", "")).name
    chemin = importation.IMPORTS / nom
    if not nom.startswith("tmp_") or not chemin.is_file():
        return redirect(url_for("demarrer"))

    correspondance = {
        nom_champ: request.form.get(f"col_{nom_champ}", "")
        for nom_champ, _libelle, _obligatoire, _mots in importation.COLONNES
    }
    nom_origine = request.form.get("nom_origine") or "Fichier importé"

    try:
        tableau = importation.lire(chemin)
        propre, rapport = importation.normaliser(tableau, correspondance)
    except importation.ErreurImport as probleme:
        return _page_colonnes(chemin, nom_origine, erreur=str(probleme), correspondance=correspondance)

    fichier = importation.enregistrer(propre)
    donnees.activer_import(fichier, nom_origine)
    chemin.unlink(missing_ok=True)
    return redirect(url_for("accueil"))


@app.post("/demarrer/exemple")
def demarrer_exemple():
    donnees.activer_exemple()
    return redirect(url_for("accueil"))


@app.get("/api/sante")
def sante():
    return jsonify(
        {
            "statut": "ok",
            "site": "tableau de bord",
            "port": int(os.environ.get("PORT", 5080)),
            "donnees": donnees.source_active(),
            "moteur_alertes": {"en_ligne": donnees.etat_moteur()},
        }
    )


@app.errorhandler(413)
def fichier_trop_gros(_erreur):
    return (
        render_template(
            "demarrer.html",
            etape="fichier",
            source=donnees.source_active(),
            erreur=f"Fichier trop volumineux (maximum {importation.TAILLE_MAX // (1024 * 1024)} Mo).",
            extensions=sorted(importation.EXTENSIONS),
            taille_max=importation.TAILLE_MAX // (1024 * 1024),
        ),
        413,
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
