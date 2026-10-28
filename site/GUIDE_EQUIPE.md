# Guide d'équipe : brancher votre modèle sur le site

Chacun a son notebook, ses données, son modèle. Vous n'avez rien à faire sur le site, sauf donner l'adresse de votre API.

## Étapes (≈ 5 min)
1. Collez les cellules VII.2 et VII.3 du fichier `Deployment_cellules_a_copier_v4.ipynb` à la fin de votre notebook.
2. Dans le bloc « A MODIFIER » de VII.2, renseignez :
   - `MODELE` (votre pipeline entraîné), `SEUIL_MODELE`, `X_REF` (vos données d'apprentissage brutes), `FEATURES_API` (vos variables brutes) ;
   - `NOM_MODELE`, `AUTEUR`, `DESCRIPTION`, `CIBLE` (ce que mesure votre score : « Probabilité de défaut », etc.) ;
   - `PORT` : un port différent par API, de `5001` à `5006` (le site utilise le port `5000`) ;
   - facultatif : `LIBELLES` (noms lisibles des champs) et `BORNES`.
3. Exécutez VII.2 (crée le dossier `api_xxx/`) puis VII.3 (teste l'API dans le notebook). Les 4 vérifications doivent réussir.
4. Téléchargez le dossier `api_xxx/` (depuis Google Drive si vous êtes sur Colab) et lancez-le sur votre ordinateur :
   ```
   cd api_xxx
   pip install -r requirements.txt
   python api.py
   ```
5. Donnez votre adresse à la personne qui lance le site : `http://IP-DE-VOTRE-PC:PORT`.

## Règles
- Le pipeline doit **inclure tout le prétraitement** et accepter directement les variables brutes (celles de `FEATURES_API`).
- Seulement des composants scikit-learn / numpy (pas de fonction définie dans le notebook, sinon l'API ne recharge pas le fichier ; la cellule le détecte).
- Même version de scikit-learn pour tous (écrite dans `requirements.txt`).
- Un port différent par API ; les six ports réservés aux modèles sont `5001` à `5006`.
- Le site utilise `5000` et n'est pas un port de modèle.

## Problèmes fréquents
| Message | Cause | Solution |
|---|---|---|
| `AssertionError: ... fonction définie dans le notebook` | `FunctionTransformer(ma_fonction)` ou classe maison | Remplacer par des composants scikit-learn |
| `KeyError` / colonne manquante dans le test | `X_REF` ou `FEATURES_API` ne correspond pas à ce que le pipeline attend | Utiliser les colonnes brutes d'avant le pipeline |
| `InconsistentVersionWarning` au lancement | Version de scikit-learn différente | `pip install -r requirements.txt` |
| Le site affiche l'API « hors ligne » | API non lancée, mauvais port, pare-feu | Vérifier `http://localhost:PORT/api/health` ; pour d'autres PC, utiliser l'IP et autoriser le port |
| `Address already in use` | Port déjà pris | Choisir un autre port modèle libre entre `5001` et `5006` et mettre à jour `site/apis.json`. |
| Un champ catégoriel a une très longue liste | Variable à beaucoup de modalités | Acceptable, ou regrouper les modalités dans le pipeline |
