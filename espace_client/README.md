# Espace client — site commercial (Banque Atlas)

Prototype du **site grand public** de la banque : présentation des cartes, questionnaire
client et offre personnalisée. Il est distinct du site conseiller (`../site`, port 5000),
qui reste l'outil interne du groupe.

- Adresse : <http://127.0.0.1:5070>
- Techno : Flask + Jinja, CSS et JavaScript maison (aucun CDN, aucune étape de build)
- Moteur : API K-Means du projet (`../api_kmeans`, port 5004)

## Lancer

Le plus simple, comme le reste du projet :

```
python lancer_tout.py        # démarre ce qui manque puis ouvre http://127.0.0.1:5070
```

Ou le site seul (les API doivent déjà tourner pour une segmentation par le modèle) :

```
cd espace_client
../venv/Scripts/python.exe app.py          # ou : python app.py
PORT=5080 python app.py                    # autre port
API_KMEANS_URL=http://127.0.0.1:5004 python app.py
```

## Pages

| Route | Rôle |
| --- | --- |
| `GET /` | page commerciale : cartes, parcours, sécurité, FAQ |
| `GET /offre` | questionnaire en deux écrans (profil, puis usage de la carte) |
| `POST /offre` | calcule et affiche l'offre personnalisée |
| `GET /api/sante` | état du site et du moteur (utilisé par `lancer_tout.py`) |

Le parcours client est : page d'accueil → questionnaire → offre (carte, plafond, arguments,
synthèse conseiller, demande). Sans JavaScript, les deux écrans s'affichent d'un bloc et le
formulaire reste utilisable.

## Comment l'offre est calculée

1. **9 questions en langage courant** (revenu, ancienneté, plafond actuel, dépenses carte,
   mode de paiement, fréquence, retraits, solde moyen, remboursement).
2. **Traduction en 17 variables** attendues par le modèle K-Means, en grandeurs annuelles :
   dépenses × 12 → `PURCHASES` ; répartition une fois / échelonné → `ONEOFF_PURCHASES` et
   `INSTALLMENTS_PURCHASES` ; fréquence ÷ 30 → `PURCHASES_FREQUENCY` ; retraits ÷ 80 TND →
   `CASH_ADVANCE_TRX` ; remboursement → `PRC_FULL_PAYMENT` et `PAYMENTS`, etc.
   Les hypothèses sont regroupées en constantes en tête de `moteur.py`.
3. **Segment → carte** : `0 Achats élevés` → Atlas Infinite, `1 Profil équilibré` →
   Atlas Essentielle, `2 Trésorerie` → Atlas Gold. **Garde-fou** : si le plafond minimal
   de cette carte dépasse trois mois de revenu net, on redescend d'un palier
   (Infinite → Gold → Essentielle) et l'offre explique pourquoi (`carte_recommandee`).
4. **Plafond** : `min(dépenses × 2,0 / 2,5 / 3,0 selon la carte, plafond de la carte,
   3 mois de revenu net)`, remonté au plancher de la carte si le revenu le permet,
   arrondi aux 100 TND.
5. **Arguments et synthèse conseiller** : chaque offre explique le profil retenu, le calcul
   du plafond et le remboursement déclaré ; la synthèse reprend le segment, les chiffres clés
   et l'action à mener (recontacter, rendez-vous trésorerie, envoyer la documentation).

## Mode dégradé

Si l'API K-Means ne répond pas, le site ne prétend pas avoir utilisé le modèle : une
segmentation approximative (`segment_estime`, documentée dans `moteur.py`) est appliquée et
la page de résultat affiche un avertissement « moteur indisponible, offre indicative »,
sans jauge de pertinence. La synthèse conseiller indique alors de reprendre la simulation.

## Vérifications effectuées

- `GET /`, `GET /offre`, `/static/*`, `/api/sante` → 200.
- `POST /offre` valide, API K-Means en marche → offre cohérente avec le revenu :
  1 200 TND de revenu / 350 TND de dépenses → Atlas Essentielle, 1 000 TND (offre ajustée) ;
  2 500 / 900 → Atlas Gold, 5 000 TND (ajustée) ; 7 000 / 2 000 → Atlas Infinite,
  15 000 TND ; profil Trésorerie → Atlas Gold.
- `POST /offre` avec champs hors bornes / choix inconnu / texte → 400 et messages par champ.
- `POST /offre` avec `API_KMEANS_URL` sur un port mort → 200, avertissement affiché,
  jauge masquée, `moteur.en_ligne = false` dans `/api/sante`.
