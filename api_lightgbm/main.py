"""LightGBM scoring API (FastAPI). Lancer : uvicorn main:app --reload"""
from pathlib import Path
from typing import Literal, get_args, get_origin

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import scoring

JOBS = Literal["admin.", "blue-collar", "entrepreneur", "housemaid", "management", "retired",
               "self-employed", "services", "student", "technician", "unemployed", "unknown"]
MONTHS = Literal["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
YN = Literal["yes", "no"]


class Client(BaseModel):
    age: int = Field(ge=18, le=100)
    job: JOBS
    marital: Literal["married", "single", "divorced"]
    education: Literal["primary", "secondary", "tertiary", "unknown"]
    default: YN
    balance: int = Field(ge=-20000, le=500000)
    housing: YN
    loan: YN
    contact: Literal["cellular", "telephone", "unknown"]
    day: int = Field(ge=1, le=31)
    month: MONTHS
    campaign: int = Field(ge=1, le=60)
    pdays: int = Field(ge=-1, le=900)
    previous: int = Field(ge=0, le=60)
    poutcome: Literal["success", "failure", "other", "unknown"]


app = FastAPI(title="LightGBM")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MODEL_NAME = "LightGBM"
AUTHOR = "Ranim Boujlel"
TARGET = "Probabilité de souscription"
DEFAULTS = {
    "age": 35, "job": "management", "marital": "single", "education": "tertiary",
    "default": "no", "balance": 500, "housing": "no", "loan": "no",
    "contact": "cellular", "day": 15, "month": "may", "campaign": 1,
    "pdays": -1, "previous": 0, "poutcome": "unknown",
}


def describe_fields():
    fields = []
    for name, field in Client.model_fields.items():
        base = {"nom": name, "libelle": name.replace("_", " ").capitalize()}
        if get_origin(field.annotation) is Literal:
            options = list(get_args(field.annotation))
            fields.append({**base, "type": "choix", "options": options, "defaut": DEFAULTS[name]})
            continue

        limits = {
            key: value
            for constraint in field.metadata
            for key, value in (("min", getattr(constraint, "ge", None)),
                               ("max", getattr(constraint, "le", None)))
            if value is not None
        }
        fields.append({
            **base,
            "type": "nombre",
            "min": limits["min"],
            "max": limits["max"],
            "entier": field.annotation is int,
            "defaut": DEFAULTS[name],
        })
    return fields


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": scoring.MODE, "threshold": scoring.threshold()}


@app.get("/api/info")
def info():
    mode_description = (
        "Modèle LightGBM chargé."
        if scoring.MODE == "model"
        else "Mode démonstration : le modèle entraîné n'est pas présent."
    )
    return {
        "nom": MODEL_NAME,
        "auteur": AUTHOR,
        "description": mode_description,
        "cible": TARGET,
        "seuil": scoring.threshold(),
        "champs": describe_fields(),
    }


@app.post("/api/predict")
def predict(client: Client):
    score = scoring.predict(client.model_dump())
    thr = scoring.threshold()
    return {
        "score": round(score, 4),
        "threshold": thr,
        "contact": score >= thr,
        "mode": scoring.MODE,
        "modele_nom": MODEL_NAME,
        "auteur": AUTHOR,
        "cible": TARGET,
        "score_pct": round(score * 100, 1),
        "seuil": thr,
        "contacter": score >= thr,
    }


STATIC = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
