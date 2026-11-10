# Tableau de bord banque — pilotage du portefeuille clients

Petit prototype de l'interface **destinée au conseiller**, par opposition à l'espace client
commercial (`../espace_client`, port 5070). Il répond à une question simple : une fois les
clients segmentés, qu'est-ce qu'un conseiller regarde et qu'est-ce qu'il fait ?

- Adresse : <http://127.0.0.1:5080> — s'ouvre sur la page **Charger le portefeuille**
- Données : le fichier importé par le conseiller, ou à défaut
  `../api_isolation_forest/bank_transactions_data_2.csv` (495 comptes, 2 512 transactions, 12 mois — montants en TND)
- Exemple d'import : `tableau_bord/exemple_banque.csv` (40 comptes synthétiques, format français)
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

## Page de démarrage : charger les données de la banque

`/demarrer` est une page autonome, **sans barre de navigation** : tant qu'aucun jeu de données n'a été
choisi, toutes les autres adresses renvoient vers elle (302) et une adresse inconnue répond 404. Elle
propose :

1. **un grand dépôt de fichier** (glisser-déposer ou sélection) : CSV, TSV, TXT ou JSON, 30 Mo maximum ;
   les classeurs Excel doivent être enregistrés en CSV, le message le dit explicitement ;
2. **l'association des colonnes** : le fichier est analysé, un aperçu de six lignes s'affiche et chaque
   colonne attendue (compte, date, montant, sens, solde, canal, profession, âge, durée, tentatives de
   connexion) est pré-associée par ressemblance de nom, accents et ponctuation ignorés ;
3. **l'ouverture du tableau de bord** : les lignes inexploitables (date ou montant illisible, sens
   inconnu) sont écartées et comptées avant d'écrire `imports/transactions_<horodatage>.csv`.

Le fichier normalisé devient la source de **tout** le prototype : indicateurs, segments RFM, alertes
et fiches clients. Le pied de page rappelle la source et permet d'en charger une autre ; un nouvel
import remplace entièrement le précédent. « Explorer avec les données d'exemple » ouvre le jeu de
démonstration (495 comptes) sans rien importer.

Formats compris : séparateurs `,` `;` `tabulation` `|` détectés automatiquement, dates `jj/mm/aaaa`
ou ISO, montants `1 234,56` ou `1,234.56` (les symboles monétaires sont ignorés), JSON en liste
d'objets. Les fichiers déposés et l'état local restent dans `imports/`, exclu de git.

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
triés par volume, notes R, F et M visibles. Un clic sur un compte ouvre sa fiche.

## Fiche client : les cinq modèles du projet

`/client/<compte>` (accessible depuis un segment ou depuis les listes de la vue d'ensemble) applique
les modèles des autres membres au compte, avec leurs entrées visibles et modifiables.

| Carte | API | Modèle | Auteur | Question | Entrées pré-remplies |
| --- | --- | --- | --- | --- | --- |
| Risque de défaut | 5005 | Gradient Boosting | Siwar Raouafi | Défaut de paiement le mois prochain | 6 mois reconstitués : factures = débits, paiements = crédits, retard = mois sans paiement |
| Profil comportemental | 5004 | K-Means | Hedi Hassan | Profil de clientèle (3 segments) | 17 variables de carte projetées : solde, achats, retraits, opérations, ancienneté |
| Propension à souscrire | 5006 | LightGBM | Ranim Boujlel | Souscription d'un produit d'épargne | Âge, métier et solde réels ; situation et logement à confirmer |
| Actifs bancaires estimés | 5002 | Lasso | Souha Mabrouk | Valeur d'actifs bancaires | Simulateur : revenus et patrimoine ne sont pas dans le jeu de données |
| Potentiel de revenu élevé | 5001 | Random Forest | Mahdi Lakhoua | Revenu supérieur au seuil du modèle | Âge et profession réels ; études et situation au référentiel |

Chaque carte affiche le score, le verdict en clair, le seuil du modèle, et un bloc **Ajuster les
entrées** qui détaille les champs réellement envoyés à l'API. Le bouton « Recalculer » renvoie le
formulaire à la fiche, qui réaffiche le score mis à jour (testé : risque de défaut 75,5 % → 50,8 %
avec une limite de crédit et des paiements corrigés). « Réinitialiser », à côté, remet dans le
formulaire les valeurs proposées pour ce client — côté navigateur sans rechargement, et côté serveur
si le formulaire est soumis avec `action=reinitialiser`. Si une API est arrêtée, seule sa carte passe
en « hors ligne » ; les autres restent calculées.

**Attention aux deux segmentations.** Les segments du tableau de bord (Champions, Loyaux…) sont des
segments **RFM** calculés localement ; le K-Means de Hedi apparaît comme *profil comportemental*
par client, avec sa confiance d'appartenance. Les deux lectures cohabitent sans se contredire :
RFM dit quoi faire, K-Means dit à quoi le client ressemble.

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
- L'import n'est pas un ETL : il ne dédoublonne pas les transactions, ne convertit pas les devises et
  ne joint pas un référentiel clients. Il vérifie seulement que le fichier permet de calculer des
  segments (20 lignes et 5 comptes minimum).
- `imports/etat.json` mémorise la source choisie ; supprimez-le pour revoir la page de démarrage au
  prochain lancement.
- Pas d'authentification ni de gestion des rôles : c'est une maquette locale.
- Les alertes examinent six transactions par affichage (appels HTTP au modèle), pas tout le flux.
- Les entrées des modèles Gradient Boosting, K-Means et LightGBM sont **projetées** depuis les
  transactions : c'est une démonstration d'intégration, pas un scoring de production. Le détail de
  la projection est visible dans le formulaire de chaque carte et dans `valeurs_proposees()`.
- Les modèles Lasso et Random Forest attendent des données patrimoniales et socio-démographiques
  absentes du jeu : leurs cartes sont des simulateurs, à remplir avec le conseiller.

## Vérifications effectuées

- `GET /`, `/segment/champions`, `/segment/a_reveiller`, `/static/style.css`, `/api/sante` → 200 ;
  `/segment/inconnu` → 404.
- Les cinq segments sortent avec des effectifs cohérents : Champions 110, Loyaux 100,
  Prometteurs 49, À réveiller 53, Dormants 183 (495 comptes au total).
- Les alertes sont affichées avec le score du modèle et le seuil renvoyés par l'API 5003 ;
  si l'API est arrêtée, la page affiche un encart « modèle hors ligne » à la place.
- `lancer_tout.py` ouvre bien 5070 puis 5080 (vérifié avec `webbrowser.open` instrumenté).
- Fiche client : `/client/AC00020` → 200 en 0,6 s avec les cinq scores ; `/client/ZZ99999` → 404 ;
  recalcul POST du risque de défaut pris en compte ; une API déplacée sur un port mort fait passer
  uniquement sa carte en « hors ligne ».
- Démarrage : avant tout choix, `/`, `/segment/…` et `/client/…` → 302 vers `/demarrer`, adresse
  inconnue → 404, `/demarrer` sans barre latérale ; « données d'exemple » puis un import testé de
  bout en bout donnent 200 sur les mêmes adresses.
- Reset : `LIMIT_BAL` proposé 8 430 → recalculé 999 999 → 8 430 après « Réinitialiser ».
- Import testé de bout en bout avec `exemple_banque.csv` (séparateur `;`, dates `jj/mm/aaaa`, montants
  à virgule, en-têtes accentués) : 8 colonnes associées automatiquement, 400 lignes et 40 comptes
  repris, tableau de bord et fiche client affichés ; mapping incomplet → message « Associez aussi… » ;
  `.xlsx` refusé avec la consigne d'export CSV.
