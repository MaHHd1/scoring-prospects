# Site de la banque – Espace conseiller

Le site ne contient aucun modèle. Il lit `apis.json`, interroge chaque API (`GET /api/info`),
construit le formulaire à partir des champs déclarés par l'API choisie, puis appelle `POST /api/predict`.

## Lancer
```
pip install flask requests
python site.py            # http://127.0.0.1:5000   (PORT=8000 python site.py pour changer de port)
```
Ajouter le modèle d'un coéquipier : ajouter `{"url": "http://ADRESSE:PORT"}` dans `apis.json` (pas de redémarrage nécessaire, cliquer « Actualiser »).

## Comparer des modèles différents
En mode comparaison, le formulaire réunit les champs de tous les modèles en ligne ; chaque API reçoit uniquement ses propres champs.
