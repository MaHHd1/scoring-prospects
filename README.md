# Scoring Prospects

A local web application for exploring prospect-scoring and customer-segmentation models. The
website provides the interface; each model runs in its own API process and loads its own saved
model file.

## Contents

- [How the application works](#how-the-application-works)
- [Requirements and setup](#requirements-and-setup)
- [Run everything from VS Code](#run-everything-from-vs-code)
- [Run services manually](#run-services-manually)
- [Models included in this repository](#models-included-in-this-repository)
- [API contract](#api-contract)
- [Connect another team model](#connect-another-team-model)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)

## How the application works

The browser talks to the website on port `5000`. The website reads the API URLs from
[`site/apis.json`](site/apis.json), requests model information from each API, and builds the
input form using the fields returned by the online models. When a user requests a score, the
website sends the corresponding input to the selected model API. The API returns a result for
the website to display.

The website does not load or execute model files and does not run the notebooks. Each API loads
its saved model when that API process starts. The repository includes Random Forest, Lasso
Regression, Isolation Forest, K-Means, Gradient Boosting, and LightGBM APIs. The app runner starts
all six.

The notebooks are used to develop and train models. The saved model artifact and its API code
are what serve predictions while the application is running. Retraining a model requires
running its training workflow and saving a new artifact; restarting an API loads the artifact
currently on disk.

## Requirements and setup

Python 3.10 or later is required. Clone the repository and run the following from its root.
The shared root [`requirements.txt`](requirements.txt) pins the compatible dependencies for
the website and all six APIs; use it rather than installing each API's requirements separately.

On Windows, open PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

On macOS or Linux:

```bash
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

Once dependencies are installed, start the website and all APIs with
`python lancer_tout.py` (or use the VS Code **Run all scoring services** profile below).
The runner uses the repository's virtual environment on Windows and macOS/Linux.

The checked-in Lasso artifact was serialized with scikit-learn `1.9.1`. It currently loads and
predicts with the shared `1.6.1` dependency but emits compatibility warnings; retrain it before
relying on it:

```powershell
.\venv\Scripts\python.exe .\api_Lasso_Regression\train_model.py
```

The training CSV is included in `api_Lasso_Regression`. Use compatible dependency versions when
training or replacing any saved model artifact.

## Run everything from VS Code

1. Open the repository root as the VS Code workspace.
2. To use the editor's **Run Python File** button, open [`lancer_tout.py`](lancer_tout.py) and
   click **Run Python File**. That button runs only the currently open Python file.
3. Alternatively, open **Run and Debug**, select **Run all scoring services**, and press **F5**.
   The profile is defined in [`.vscode/launch.json`](.vscode/launch.json).

The runner starts services that are not already listening, waits for their health checks, and
opens `http://127.0.0.1:5000` in the browser. It leaves already-running services alone. Keep the
runner's terminal open while using the app; press **Ctrl+C** there to stop the services it
started.

## Run services manually

Create and activate a virtual environment and install the dependencies as described above.
Then run each service in its own terminal from the repository root:

```powershell
.\venv\Scripts\python.exe .\api_random_forest\api.py
```

```powershell
.\venv\Scripts\python.exe .\api_Lasso_Regression\api.py
```

```powershell
$env:PORT = "5003"
.\venv\Scripts\python.exe .\api_isolation_forest\api.py
```

```powershell
$env:PORT = "5005"
.\venv\Scripts\python.exe ".\api_Gradient Boosting\api.py"
```

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --app-dir .\api_lightgbm --host 127.0.0.1 --port 5006
```

```powershell
$env:PORT = "5004"
.\venv\Scripts\python.exe .\api_kmeans\api.py
```

```powershell
.\venv\Scripts\python.exe .\site\site.py
```

Open `http://127.0.0.1:5000`. The APIs use ports `5001` (Random Forest), `5002` (Lasso),
`5003` (Isolation Forest), `5004` (K-Means), `5005` (Gradient Boosting), and `5006` (LightGBM);
the website uses port `5000`. The K-Means and Gradient Boosting commands set their ports
explicitly to match the runner/site configuration. In PowerShell, environment variables are set
with `$env:NAME = "value"`; in other shells, use that shell's environment-variable syntax.

## Models included in this repository

### Random Forest

- API: [`api_random_forest/api.py`](api_random_forest/api.py)
- Saved model: `api_random_forest/modele.joblib`
- Default API port: `5001`
- The API loads the saved pipeline, validates the requested input fields, and returns a
  probability score and decision threshold.
- Its `requirements.txt` lists its Python dependencies.

### LightGBM — bank marketing

- API: [`api_lightgbm/main.py`](api_lightgbm/main.py) (FastAPI)
- Saved model: `api_lightgbm/modele_final_membre4.joblib` (optional; demo scoring is used if absent)
- Default API port: `5006`
- Identifies prospects likely to subscribe to a term deposit, using the Bank Marketing fields
  declared by the API.
- The trained `modele_final_membre4.joblib` artifact is not included in the repository. Without
  it, the API remains available in demo mode; provide the artifact to use Ranim's trained model.
- The app runner starts this API with Uvicorn. Install its dependencies from
  the shared root [`requirements.txt`](requirements.txt) along with the other services.

### Lasso Regression — bank asset value

- API: [`api_Lasso_Regression/api.py`](api_Lasso_Regression/api.py)
- Saved pipeline: [`api_Lasso_Regression/modele_lasso.joblib`](api_Lasso_Regression/modele_lasso.joblib)
- Default API port: `5002`
- Estimates `bank_asset_value` using five financial fields from the loan approval dataset.
  The pipeline imputes missing values, standardizes the inputs, and applies Lasso Regression.
- [`api_Lasso_Regression/train_model.py`](api_Lasso_Regression/train_model.py) retrains the
  pipeline from the included `loan_approval_dataset.csv`.
- Compatibility note: the committed artifact was trained with scikit-learn `1.9.1`, not the
  shared `1.6.1` dependency. It loads with a warning in the shared environment; retraining as
  described above regenerates the artifact with the installed version.

### K-Means customer segmentation

- API: [`api_kmeans/api.py`](api_kmeans/api.py)
- Saved pipeline: `api_kmeans/modele_kmeans.joblib`
- Default API port: `5004`
- The pipeline applies median imputation, standardization, and K-Means clustering to 17
  behavioral variables.
- The API assigns the nearest cluster center. Its displayed confidence is derived from the
  distance to the nearest and second-nearest centers; it is not a calibrated probability.
- [`api_kmeans/train_model.py`](api_kmeans/train_model.py) can retrain and save the pipeline
  when the source dataset is available. The script looks for `CC GENERAL.csv` in its folder or
  a parent folder, or accepts the CSV path as an argument.

### Gradient Boosting — credit default

- API: [`api_Gradient Boosting/api.py`](api_Gradient%20Boosting/api.py)
- Saved pipeline: `api_Gradient Boosting/modele_defaut_paiement.joblib`
- Default API port: `5005`
- Predicts credit-card payment default from customer repayment history and credit-limit fields.
- [`api_Gradient Boosting/train_model.py`](api_Gradient%20Boosting/train_model.py) can retrain
  the model from the included `UCI_Credit_Card.csv`.
- The app runner starts this API on port `5005`.

### Isolation Forest (transactions atypiques)

- API: [`api_isolation_forest/api.py`](api_isolation_forest/api.py)
- Saved pipeline: `api_isolation_forest/modele_isolation_forest.joblib`
- Default API port: `5003`
- Unsupervised anomaly detection on bank transactions: ratio feature (amount / balance),
  one-hot encoding of categorical fields, then an Isolation Forest (1000 trees, 5 % alerts).
- The displayed score is an anomaly score (0-100), not a fraud probability.
- [`api_isolation_forest/train_model.py`](api_isolation_forest/train_model.py) retrains and saves
  the pipeline from `bank_transactions_data_2.csv`. If the saved model cannot be loaded (for
  example a different scikit-learn version), the API retrains it automatically at startup.

The website's `apis.json` lists six model APIs on ports `5001` through `5006`, including Ranim's
LightGBM API on `5006`. The website itself uses port `5000`. Cloning and running the repository
starts the APIs on that computer; it does not publish them to the internet. To share one running
instance across the internet, deploy the site and APIs to a reachable server and configure their
addresses and network access accordingly.

## API contract

Each model API should expose:

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Health check used by the app runner and team members |
| `GET /api/info` | Model metadata and input field descriptions used to build the website form |
| `POST /api/predict` | Accept model input as JSON and return the model result as JSON |

The website exposes:

| Method and path | Purpose |
|---|---|
| `GET /` | Render the scoring page |
| `GET /api/models` | Return the configured APIs and their online status |
| `POST /api/score` | Score input with one or more selected APIs |

`POST /api/score` expects a JSON object with an `indices` array and a `donnees` object. The
indices correspond to the API order in `site/apis.json`. For example:

```json
{
  "indices": [0],
  "donnees": {
    "example_field": 1
  }
}
```

The exact fields required in `donnees` depend on the selected model and are declared by its
`GET /api/info` response.

## Connect another team model

1. Implement the API contract above. Return the model's input field names, labels, types, and
   any applicable options or bounds from `GET /api/info`.
2. Ensure the saved pipeline includes all preprocessing required for inference and accepts the
   raw fields declared by the API.
3. Use a distinct model port; the website uses port `5000` and this repository currently uses
   `5001` through `5006` (LightGBM uses `5006`). For an additional API, choose another unused
   port and add its URL to `site/apis.json`.
4. Start the API and check `http://localhost:PORT/api/health`.
5. Add its URL to the `apis` list in [`site/apis.json`](site/apis.json). For an API on the same
   computer, use `http://127.0.0.1:PORT`. For an API on another computer, use its reachable IP
   address and ensure network/firewall access is allowed.
6. In the website, click **Actualiser les services**. The website rereads `apis.json` when it
   requests models, so a restart is not required for a URL change.

Keep the model's training and inference dependencies compatible, especially the scikit-learn
version used to save and load a joblib model. Avoid custom notebook-only Python functions in a
serialized pipeline, as the API process may not be able to import them.

The existing French team guide has additional model-integration notes and common issues:
[`site/GUIDE_EQUIPE.md`](site/GUIDE_EQUIPE.md).

## Troubleshooting

| Symptom | Likely cause and resolution |
|---|---|
| The page does not open | Confirm the website is responding at `http://127.0.0.1:5000`, and check the runner's terminal for startup errors. |
| An API appears offline | Confirm that API is running, that its URL and port match `site/apis.json`, and that `http://localhost:PORT/api/health` responds. |
| `venv` is missing | Create it at the repository root with `py -m venv venv`, then install the dependencies listed above. |
| `Address already in use` | Another process is using the port. Stop that service or configure a different port and update the matching URL in `site/apis.json`. |
| Model loading reports a version warning or error | Install a scikit-learn version compatible with the one used to save the model; see the API's requirements file. |
| An input field is missing or rejected | Compare the fields sent by the website with the model's `GET /api/info` response and the API's input validation. |

The Flask development servers are intended for local development and demonstrations, not
production deployment.

## Project structure

```text
.
├── requirements.txt            # Shared pinned runtime dependencies for all services
├── .vscode/
│   └── launch.json             # VS Code F5 profile for the full app
├── api_Gradient Boosting/
│   ├── api.py                  # Gradient Boosting Flask API
│   ├── modele_defaut_paiement.joblib
│   ├── preparation_defaut.py   # Custom sklearn transformer for the pipeline
│   ├── requirements.txt
│   └── train_model.py
├── api_kmeans/
│   ├── api.py                  # K-Means Flask API
│   ├── modele_kmeans.joblib    # Trained K-Means pipeline
│   ├── requirements.txt
│   └── train_model.py          # Retrain and save the pipeline
├── api_Lasso_Regression/
│   ├── api.py                  # Lasso bank-asset regression API
│   ├── modele_lasso.joblib     # Trained Lasso pipeline
│   ├── requirements.txt
│   └── train_model.py
├── api_isolation_forest/
│   ├── api.py                  # Transaction anomaly-detection API
│   ├── modele_isolation_forest.joblib
│   ├── requirements.txt
│   └── train_model.py
├── api_lightgbm/
│   ├── main.py                 # LightGBM FastAPI API
│   ├── scoring.py              # Model and demo scoring
│   └── requirements.txt
├── api_random_forest/
│   ├── api.py                  # Random Forest Flask API
│   ├── modele.joblib           # Trained Random Forest model
│   └── requirements.txt
├── site/
│   ├── apis.json               # API URLs consumed by the website
│   ├── site.py                 # Website and scoring proxy endpoints
│   ├── templates/
│   ├── README.md               # Website-specific notes
│   └── GUIDE_EQUIPE.md         # French team integration guide
└── lancer_tout.py              # Starts services and opens the browser
```
