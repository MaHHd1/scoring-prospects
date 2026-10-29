#!/usr/bin/env python3
"""Lance tout le projet d'un seul geste : les 2 API + le site, puis ouvre le navigateur.

Analogie avec ce que vous connaissez deja (Java / Angular) :
  - pom.xml / package.json  ->  requirements.txt   (les dependances, deja present)
  - application.properties  ->  les PORT ci-dessous (la configuration)
  - bouton Run / ng serve    ->  CE script, declenche par .vscode/launch.json (F5 dans VS Code)

Dans VS Code, « Run Python File » lance uniquement le fichier ouvert. Pour demarrer tout le
projet avec ce bouton, ouvrez ce fichier ; sinon utilisez F5 et choisissez « Run all scoring services ».

Usage :
    python lancer_tout.py       # demarre ce qui manque et ouvre http://127.0.0.1:5000
    Ctrl+C                      # arrete les services que CE script a demarres

Un service deja en marche (p. ex. une API ouverte dans un autre terminal) est
detecte et laisse tel quel : il ne sera pas demarre une deuxieme fois.
"""

import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from socket import AF_INET, SOCK_STREAM, socket

BASE = Path(__file__).resolve().parent
SITE_URL = "http://127.0.0.1:5000"
DELAI_ATTENTE = 30  # secondes maximum d'attente par service

# Messages immediats, meme si la sortie est redirigee vers un fichier.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# (nom, sous-dossier, port, script, chemin de sante HTTP)
SERVICES = [
    ("API Random Forest (Mahdi Lakhoua)", "api_random_forest", 5001, "api.py", "/api/health"),
    ("API Isolation Forest (Mehdi Dhib)", "api_isolation_forest", 5003, "api.py", "/api/health"),
    ("API K-Means (Hedi Hassan)",         "api_kmeans",        5004, "api.py", "/api/health"),
    ("Site web (Banque Atlas)",           "site",              5000, "site.py", "/"),
]


def python_venv() -> str:
    """Python du venv du depot (les deux API et le site partagent la meme version)."""
    candidats = [
        BASE / "venv" / "Scripts" / "python.exe",  # Windows
        BASE / "venv" / "bin" / "python",          # macOS / Linux
    ]
    for chemin in candidats:
        if chemin.exists():
            return str(chemin)
    sys.exit("venv introuvable dans " + str(BASE) + " (lancez d'abord : python -m venv venv)")


def port_occupe(port: int) -> bool:
    with socket(AF_INET, SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def pret(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as reponse:
            return reponse.status == 200
    except Exception:
        return False


def main() -> int:
    exe = python_venv()
    env_base = {**os.environ, "PYTHONUTF8": "1"}
    enfants = []

    # 1. Demarrage (ce qui n'est pas deja en marche)
    for nom, dossier, port, script, _ in SERVICES:
        if port_occupe(port):
            print(f"[deja en marche] {nom} (port {port})")
            continue
        enfant = subprocess.Popen(
            [exe, script],
            cwd=BASE / dossier,
            env={**env_base, "PORT": str(port)},
        )
        enfants.append((nom, port, enfant))
        print(f"[demarrage]      {nom} (port {port}, pid {enfant.pid})")

    # 2. Attente de la reponse de chaque service
    echecs = []
    for nom, _, port, _, chemin_sante in SERVICES:
        url = f"http://127.0.0.1:{port}{chemin_sante}"
        fin = time.time() + DELAI_ATTENTE
        while time.time() < fin and not pret(url):
            time.sleep(0.5)
        if pret(url):
            print(f"[ok]             {nom} repond sur le port {port}")
        else:
            print(f"[ECHEC]          {nom} ne repond pas ({url})")
            echecs.append(nom)

    # 3. Ouverture du site
    if pret(SITE_URL):
        print(f"\nOuverture du site : {SITE_URL}")
        webbrowser.open(SITE_URL)
    else:
        print(f"\nLe site n'a pas repondu sur {SITE_URL} : voir les messages ci-dessus.")
        for _, _, enfant in enfants:
            if enfant.poll() is None:
                enfant.terminate()
        return 1

    if echecs:
        print("Services absents (le site les affichera 'Hors ligne') : " + ", ".join(echecs))
    print("Ctrl+C pour arreter les services demarres par ce script.\n")

    # 4. Supervision : on reste vivant jusqu'a Ctrl+C
    arretes = set()
    try:
        while True:
            time.sleep(1)
            for nom, _, enfant in enfants:
                if enfant in arretes:
                    continue
                if enfant.poll() is not None:
                    arretes.add(enfant)
                    print(f"[arrete]         {nom} (code {enfant.returncode})")
            if len(arretes) == len(enfants):
                print("Tous les services demarres par ce script sont arretes.")
                return 0
    except KeyboardInterrupt:
        print("\nArret des services...")
    finally:
        for _, _, enfant in enfants:
            if enfant.poll() is None:
                enfant.terminate()
        for _, _, enfant in enfants:
            try:
                enfant.wait(timeout=5)
            except Exception:
                enfant.kill()
    print("Termine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())