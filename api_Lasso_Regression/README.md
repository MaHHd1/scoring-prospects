# Prédiction de la valeur des actifs bancaires — Lasso Regression

Ce dossier contient les fichiers de base pour exposer le modèle Lasso du projet de machine learning.

## Variables utilisées

- `income_annum`
- `luxury_assets_value`
- `loan_amount`
- `commercial_assets_value`
- `residential_assets_value`

Variable cible : `bank_asset_value`.

## 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

## 2. Placer le dataset

Placez `loan_approval_dataset.csv` dans ce dossier, ou indiquez le chemin complet lors de l'entraînement.

## 3. Entraîner et sauvegarder le modèle

```bash
python train_model.py loan_approval_dataset.csv
```

Cette commande crée `modele_lasso.joblib`. Le fichier modèle n'est pas inclus dans ce paquet : il doit être généré à partir du dataset réel.

## 4. Lancer l'API

```bash
python api.py
```

L'API est disponible par défaut sur `http://127.0.0.1:5002` (slot réservé de l'équipe).

## Endpoints

- `GET /api/health`
- `GET /api/info`
- `POST /api/predict`

Exemple de corps JSON pour `/api/predict` :

```json
{
  "income_annum": 5000000,
  "luxury_assets_value": 5000000,
  "loan_amount": 5000000,
  "commercial_assets_value": 3000000,
  "residential_assets_value": 3000000
}
```

## Important

Les métriques MAE, RMSE et R² renseignées dans `/api/info` sont celles partagées depuis la validation croisée actuelle. Elles ne sont pas recalculées automatiquement par l'API. Les bornes du formulaire sont indicatives et doivent être ajustées selon les statistiques exactes du dataset et l'unité monétaire employée.
