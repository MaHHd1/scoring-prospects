"""Etape de preparation partagee par train_model.py et api.py.

La fonction vit dans un fichier .py (et non dans le notebook) pour que joblib
puisse la retrouver quand l'API recharge le modele (meme principe que
preparation_defaut.py de l'API Gradient Boosting).
"""


def ajouter_ratio(X):
    """Ajoute AmountToBalance = TransactionAmount / AccountBalance (notebook, section 2.1)."""
    X = X.copy()
    X["AmountToBalance"] = X["TransactionAmount"] / X["AccountBalance"]
    return X
