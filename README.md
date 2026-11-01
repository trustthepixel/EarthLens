# EARTHLENS

earthLens is a Streamlit platform for checking the integrity of Sentinel-2 L2A satellite-image chips. It combines a map-based dashboard, a FastAPI ground station, an ONNX image detector loaded from Hugging Face, cryptographic source verification, and image forensics.

The dashboard provides area analysis and live monitoring, plus workspaces for image processing, controlled attack demonstrations, forensics and verification, audit events, model evaluation, and system status. The live area input is fixed at **256 × 256 pixels at 10 m resolution** (2.56 km square), matching the model contract.

## How the platform runs

```text
Copernicus / prepared chip
          │
          ▼
 Streamlit dashboard ── signed chip packet ──► FastAPI ground station
          │                                         │
          │                                  signature and replay checks
          │                                  ONNX detector from Hugging Face
          ◄──────────── result and evidence ────────┘
```

For local backend analysis, the dashboard and API run as separate processes on the same computer. The dashboard signs each chip with a locally provisioned Ed25519 key. The API must trust the matching public key. The API loads the ONNX model from the configured Hugging Face repository and returns the analysis and verification evidence.

## Run on Windows

Use Python 3.12 and PowerShell. Open the project folder in PowerShell. If you are cloning the repository, replace the repository URL below with the GitHub URL you use:

```powershell
git clone <repository-url> earthLens
cd earthLens
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

The runtime model is public and is fetched from Hugging Face when it is not already present locally. No Hugging Face token is required for the public model. Keep the model files local; they are excluded from Git.

### 1. Provision the source key once

In a PowerShell window in the project folder, generate the local keypair if you have not already provisioned it:

```powershell
$hasPrivateKey = Test-Path .\keys\source_private.pem
$hasTrustedPublicKey = Test-Path .\trusted_keys\source.pem
if (-not $hasPrivateKey -and -not $hasTrustedPublicKey) {
    .\.venv\Scripts\python.exe -m scripts.provision
} elseif ($hasPrivateKey -and $hasTrustedPublicKey) {
    Write-Host "The source keypair already exists; keeping it."
} else {
    throw "Only one key file exists. Restore its matching partner before starting the API."
}
```

The command creates `keys/source_private.pem` and the matching public key at `trusted_keys/source.pem`. The private key is used by the dashboard; the public key is loaded by the API. Keep both local and never commit either key. Do not regenerate the pair once provisioned: the public and private keys must remain a matching pair.

### 2. Start the backend API

Open a **second** PowerShell window in the project folder. Set the model repository in this window, then start the API:

```powershell
$env:HF_MODEL_REPO = "trustthepixel/trust-the-pixel-detector"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Leave this window open. The first start may take time while the model files are downloaded and checked. The API loads the public keys and model during startup, so start or restart it after provisioning the keypair or downloading the model.

In another PowerShell window, verify API readiness:

```powershell
$health = Invoke-RestMethod "http://127.0.0.1:8000/health"
$health | Select-Object ok, trusted_keys, error
```

The API is ready when `ok` is `True`, `error` is empty, and `trusted_keys` is at least `1`.

### 3. Start the dashboard with backend settings

Open a **third** PowerShell window in the project folder. Set the dashboard settings in this window before launching Streamlit. Environment variables are process-specific, so setting them only in the API window does not configure the dashboard.

```powershell
$env:HF_MODEL_REPO = "trustthepixel/trust-the-pixel-detector"
$env:TP_API_URL = "http://127.0.0.1:8000/health"
$env:TP_SOURCE_PRIVATE_KEY = Get-Content -Raw .\keys\source_private.pem
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`. Keep the API and Streamlit terminal windows open while using the platform.

If the backend is hosted on another machine, set `TP_API_URL` to that machine's reachable HTTPS `/health` URL instead. Do not use `127.0.0.1` for a remote backend: it refers to the computer running Streamlit.

### 4. Confirm all configured services

Open **System details** in the sidebar. For the desktop configuration above, confirm:

| Service | Expected status | What it means |
| --- | --- | --- |
| Hugging Face repository configured | Yes | `HF_MODEL_REPO` is set for the dashboard. |
| Source signing key configured | Yes | Streamlit loaded `keys/source_private.pem`. |
| Source key trusted by backend | Yes | The API loaded the matching `trusted_keys/source.pem`. |
| Backend API | Connected | The configured `/health` endpoint reports `ok: true`. |
| Model runtime | Ready | The backend model initialized and passed its readiness check. |

The dashboard must be started after setting its variables. If you change a setting, stop Streamlit with Ctrl+C and start it again from the same configured PowerShell window.

## Use the dashboard

- **Analyze area:** select a point on the map, choose a live Copernicus acquisition or prepared unseen chip, then analyze. Live acquisition needs Internet access and a usable Microsoft Planetary Computer response. A particular point or date may not have a usable full chip; try a nearby point or another acquisition date.
- **Live monitor:** view events reported by the configured API. The API must remain running.
- **Image processing:** inspect the analyzed chip and its true-colour, NDVI, and model heatmap layers.
- **Attack Lab:** apply controlled changes to a chip and compare the resulting evidence. This is a local demonstration feature; see the [attacker lab guide](attacker/README.md) for direct-feed and isolated proxy setup.
- **Forensics & verification:** review provenance, integrity, replay, and model evidence.
- **Other workspaces:** review audit events, model evaluation, map information, and service configuration.

If Internet or Copernicus access is unavailable, use the prepared offline data option when available. Basemap tiles also require Internet access; the map provides a no-tile fallback. The model input must remain four `uint16` bands in `B02`, `B03`, `B04`, `B08` order at exactly `256 × 256`. Preprocessing applies `(DN - offset) / 10000`, clipped to `[0, 1.5]`; do not resize or normalize the chip again.

## Troubleshooting

- **API not configured:** set `TP_API_URL` in the PowerShell window used to start Streamlit, then restart Streamlit.
- **API unavailable / `ok: false`:** keep the API terminal open and inspect its startup output. Set `HF_MODEL_REPO` in the API window and restart the API after model files are ready.
- **Source signing key configured: No:** set `TP_SOURCE_PRIVATE_KEY` in the Streamlit window using the command above.
- **Source key trusted by backend: No:** make sure `trusted_keys/source.pem` matches `keys/source_private.pem`, then restart the API so it reloads the trusted public key.
- **Area unavailable:** select another date or a nearby point. Scenes can lack a valid full chip at a requested location. For CRS transformation errors, restart Streamlit so the current runtime uses Rasterio's bundled PROJ database.
- **No offline option:** confirm `unseen_pack/index.json` and its referenced prepared data are present locally.

## Security and project data

Never commit `keys/`, `trusted_keys/`, `.streamlit/secrets.toml`, `.env`, PEM files, or downloaded model weights. Do not put private keys or tokens in this README, logs, screenshots, or GitHub issues. For hosted deployment, configure `HF_MODEL_REPO`, `TP_API_URL`, and `TP_SOURCE_PRIVATE_KEY` through the service's secret settings, and make sure the API has the matching public key.

The source signature in this demonstration is generated locally; Copernicus does not sign imagery through this workflow. A valid signature proves the packet matches what the provisioned key signed. It does not establish satellite origin or prove that the source imagery was untampered before signing.

## Development checks

Run the focused tests or the project check script from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\check.ps1
```

## Main folders

- `app.py`, `ui/`, `assets/`: Streamlit dashboard, map, navigation, and visual theme.
- `api.py`: FastAPI ground station.
- `tp/`: model runtime, chip validation, provenance, verification, image forensics, and Copernicus data access.
- `attacker/`: controlled packet and tampering demonstrations.
- `scripts/`: model setup, key provisioning, data preparation, and checks.
- `samples/`, `unseen_pack/`: local sample data and prepared-chip index.
- `tests/`: unit and integration tests.
