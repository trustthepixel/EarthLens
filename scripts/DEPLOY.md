# Streamlit Community Cloud Deployment

1. From the project root, push the `main` branch to the anonymous GitHub repository `trustthepixel/trust-the-pixel` with `git push origin main`. Confirm that `model/`, `docs/`, `legacy/`, `data_raw/`, `keys/`, `.env`, and PEM files are not committed.
2. Sign in to [share.streamlit.io](https://share.streamlit.io) using the anonymous GitHub account and authorize the Trust the Pixel repository.
3. Create a new Streamlit app and select repository `trustthepixel/trust-the-pixel`, branch `main`, and main file path `app.py`.
4. Open Advanced settings, select Python `3.11`, and deploy. `requirements.txt` installs the pinned cross-platform runtime packages.
5. Deploy the FastAPI ground station at a reachable HTTPS URL. Configure its runtime with `HF_MODEL_REPO` and the corresponding public verification key in `trusted_keys/`.
6. In the Streamlit app settings, add `HF_MODEL_REPO`, `TP_API_URL` (the deployed API's `/health` URL), and `TP_SOURCE_PRIVATE_KEY` (the PEM private key paired with a public key trusted by the API). Do not put private key material in repository files or logs. The public model repository requires no Hugging Face access token.
7. Wait for the dashboard and backend model checks. Confirm the API status is connected and the model input contract is validated.
8. Test both **Analyze area** and **Live monitor**. Analyze area sends a signed chip to the API's `/analyze` endpoint; Live monitor polls `/events`. If the API is unavailable, the dashboard displays recorded events and marks them as recorded. Confirm the map falls back to no tiles when basemap services cannot be reached.
9. Before a presentation, open the app in a browser in advance, wait for model loading and the self-test, and keep the page active. Streamlit Community Cloud can put inactive apps to sleep; reopen the app and allow it to wake before presenting.
