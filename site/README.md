# Site de la banque – Espace conseiller

Le site ne contient aucun modèle. Il lit `apis.json`, interroge chaque API (`GET /api/info`),
construit le formulaire à partir des champs déclarés par l'API choisie, puis appelle `POST /api/predict`.

## Lancer
```
pip install -r ..\requirements.txt
python site.py            # http://127.0.0.1:5000   (PORT=8000 python site.py pour changer de port)
```
Cette commande installe les dépendances compatibles de toutes les API et du site depuis ce dossier.
Sur macOS/Linux, utilisez `pip install -r ../requirements.txt`.
Ajouter le modèle d'un coéquipier : ajouter `{"url": "http://ADRESSE:PORT"}` dans `apis.json` (pas de redémarrage nécessaire, cliquer « Actualiser »).
L'API LightGBM de Ranim est configurée sur le port `5006` et démarre avec `lancer_tout.py`.

## Lancer tous les services depuis VS Code
Depuis la racine du dépôt, ouvrez `lancer_tout.py` puis cliquez sur « Run Python File » pour démarrer
les API et le site ensemble. Ce bouton exécute uniquement le fichier actuellement ouvert. Vous pouvez
aussi utiliser F5 et choisir « Run all scoring services » dans le menu Run and Debug.

## Comparer des modèles différents
En mode comparaison, le formulaire réunit les champs de tous les modèles en ligne ; chaque API reçoit uniquement ses propres champs.
