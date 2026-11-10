# Tableau de bord banque — pilotage du portefeuille clients

Petit prototype de l'interface **destinée au conseiller**, par opposition à l'espace client
commercial (`../espace_client`, port 5070). Il répond à une question simple : une fois les
clients segmentés, qu'est-ce qu'un conseiller regarde et qu'est-ce qu'il fait ?

- Adresse : <http://127.0.0.1:5080>
- Données : `../api_isolation_forest/bank_transactions_data_2.csv` (495 comptes, 2 512
  transactions, 12 mois — montants en TND)
- Alertes : API Isolation Forest (`../api_isolation_forest`, port 5003)
- Techno : Flask + Jinja, CSS maison, aucun CDN, aucune étape de build

## Lancer

```
python lancer_tout.py        # démarre ce qui manque, ouvre 5070 (client) puis 5080 (banque)
```

Ou seul, avec l'API d'anomalies déjà lancée :

```
cd tableau_bord
../venv/Scripts/python.exe app.py        # PORT=5081 pour changer de port
```

## Ce que montre le tableau de bord

1. **Indicateurs de portefeuille** : clients suivis, volume traité, panier moyen, clients
   inactifs depuis plus de 90 jours, part des transactions en ligne.
2. **Segments RFM** : chaque compte reçoit une note de récence (R), de fréquence (F) et de
   montant (M) de 1 à 5, calculée par quintiles sur le portefeuille. Les combinaisons donnent
   cinq profils — Champions, Loyaux, Prometteurs, À réveiller, Dormants — avec pour chacun le
   nombre de clients, la part du volume, le panier moyen et **l'action commerciale associée**.
3. **Où concentrer l'effort** : le tableau chiffré des segments (clients, volume, récence),
   pour arbitrer entre volume et nombre de clients.
4. **Clients à réveiller en priorité** : les comptes à fort volume dont la dernière transaction
   remonte, avec leur date et leur récence — la liste d'appels du conseiller.
5. **Transactions atypiques** : les transactions les plus déséquilibrées (montant / solde),
   notées par l'API Isolation Forest (score sur 100, seuil du modèle). Un score élevé signale
   un comportement inhabituel, pas une fraude confirmée.

Chaque segment a sa page (`/segment/<cle>`) avec ses indicateurs et la liste de ses clients,
triés par volume, notes R, F et M visibles.

## Pourquoi ces écrans

La segmentation seule répond à « qui sont mes clients ». Un conseiller a besoin de trois
choses de plus, et c'est ce que le prototype ajoute :

- **combien ils pèsent** (volume, part du portefeuille, panier moyen) pour prioriser ;
- **qui risque de partir** (récence élevée + volume élevé) pour agir avant la perte ;
- **qui est inhabituel** (score d'atypicité) pour contrôler sans traiter tout le monde.

L'action recommandée par segment est écrite en clair dans le code (`SEGMENTS` dans
`donnees.py`) : c'est un choix métier, facile à remplacer par la stratégie réelle de la banque.

## Limites du prototype

- RFM par quintiles : les notes sont relatives au portefeuille affiché, pas des probabilités.
- Le fichier de transactions est une démonstration ; brancher une extraction réelle demande de
  remplacer `portefeuille()` dans `donnees.py`.
- Pas d'authentification ni de gestion des rôles : c'est une maquette locale.
- Les alertes examinent six transactions par affichage (appels HTTP au modèle), pas tout le flux.

## Vérifications effectuées

- `GET /`, `/segment/champions`, `/segment/a_reveiller`, `/static/style.css`, `/api/sante` → 200 ;
  `/segment/inconnu` → 404.
- Les cinq segments sortent avec des effectifs cohérents : Champions 110, Loyaux 100,
  Prometteurs 49, À réveiller 53, Dormants 183 (495 comptes au total).
- Les alertes sont affichées avec le score du modèle et le seuil renvoyés par l'API 5003 ;
  si l'API est arrêtée, la page affiche un encart « modèle hors ligne » à la place.
- `lancer_tout.py` ouvre bien 5070 puis 5080 (vérifié avec `webbrowser.open` instrumenté).
