# AGENTS.md — Permanent Rules for the EARTHLENS Project

## 1. Project Context

EARTHLENS is a Streamlit dashboard for detecting tampering in Sentinel-2 L2A satellite images from Copernicus via Microsoft Planetary Computer. Some existing protocol, model, package, and repository identifiers retain their original `TP` or Trust the Pixel names for compatibility.

- Model: U-Net exported to ONNX.
- Model file: `model/detector.onnx`.
- Model configuration: `model/config.json`.
- Reference test data: `model/golden.npz`.
- Full documentation: `docs/`.
- Original source code: `legacy/tp_lib.py`.

**Never modify `legacy/tp_lib.py`.**

## 2. Rule #1: Development Log (Mandatory)

`DEVELOPMENT_LOGS.md` at the repository root must be updated at the end of **every development step** and before any foreseeable interruption.

- Append new entries to the end of the file.
- Never delete, overwrite, or silently rewrite previous entries.
- Use the following format:

```text
## [YYYY-MM-DD HH:MM] Step P<n>: <title>
- Status: DONE | PARTIAL | BLOCKED
- Files created or modified:
- Summary of work completed (3–8 lines):
- Commands executed and test results:
- Decisions and assumptions:
- Remaining work / exact stopping point:
```

### Status Definitions

- `DONE`: All requested work is implemented, the relevant checks pass, and the step has been completed.
- `PARTIAL`: Some work is complete, but one or more requirements remain unfinished or some checks cannot be completed.
- `BLOCKED`: Progress cannot continue because of an unresolved blocker.

Do not use `COMPLETED`, `TERMINATED`, or other status labels. The only permitted status values are `DONE`, `PARTIAL`, and `BLOCKED`.

Before declaring any step finished, reread `DEVELOPMENT_LOGS.md` and verify that the corresponding entry exists and accurately reflects the work performed.

## 3. Mandatory End-of-Step Procedure

At the end of every development step:

1. Update `DEVELOPMENT_LOGS.md` with the actual outcome.
2. Run:

   ```powershell
   .\scripts\check.ps1
   ```

   This script runs the tests and leak checks. Fix any failures and rerun the checks until they pass. If an issue cannot be resolved, record the step as `PARTIAL` or `BLOCKED`, as appropriate, and explain why.

3. Stage, commit, and push the changes:

   ```powershell
   git add -A
   git commit -m "P<n>: <title>"
   git push
   ```

4. If `git push` fails because of authentication, record the failure in `DEVELOPMENT_LOGS.md` and ask the user to run `git push` manually. Never attempt to manipulate credentials or access tokens.

**Initial setup exception:** Before Step P-1, `scripts/check.ps1` and the Git workflow may not exist. Skip unavailable checks and Git operations unless the relevant prompt explicitly requires their initial creation.

Never report a step as `DONE` merely because its code has been written. Its completion status must reflect actual implementation and verification results.

## 4. Git and Account Security Rules

### Allowed operations

- `git init`
- `git add`
- `git commit`
- `git push` to `origin` on the `main` branch
- `git config --local`

### Forbidden operations

- `git config --global`
- `git add -f`
- `git push --force`
- `git reset --hard` unless explicitly requested by the user
- Manipulating credentials, access tokens, or authentication settings, including through Windows Credential Manager
- Creating accounts
- Requesting, entering, printing, or writing passwords or access tokens

### Files that must never be tracked

Never add the following paths or files to the Git repository:

- `model/`
- `docs/`
- `legacy/`
- `data_raw/`
- `keys/`
- `*.pem`
- `.env`
- `.leakwords`

Do not bypass `.gitignore` or the repository's security checks to include excluded files.

## 5. Technical Rules

### 5.1. Model Input Contract

The model input contract must never be relaxed.

- Input tensor: `float32`, shape `(N, 4, 256, 256)`.
- Band order: `B02`, `B03`, `B04`, `B08`.
- Raw input: Sentinel-2 digital numbers (DN), stored as `uint16` before preprocessing.
- Reflectance conversion: `(DN - offset) / 10000`.
- Clip reflectance values to `[0, 1.5]`.
- Valid offsets: `0` or `1000`.
- Never apply additional normalization: normalization is already integrated into the model.

Validate inputs before inference. Reject invalid inputs or report explicit validation errors instead of silently changing the input contract.

### 5.2. No PyTorch in the Runtime Application

PyTorch must not be imported or required by the dashboard, API, or modules under `tp/`.

Use the appropriate lightweight runtime dependencies, including:

- NumPy
- OpenCV Headless
- cryptography
- ONNX Runtime
- Rasterio
- pystac-client
- planetary-computer
- Streamlit
- Plotly
- pandas

Other dependencies may be added when required by the implementation, but their versions must be pinned in `requirements.txt`.

Training and model-export notebooks may use PyTorch when necessary. This exception does not apply to the deployed runtime.

### 5.3. Legacy Code Preservation

The following modules must reproduce the corresponding logic from `legacy/tp_lib.py` without changing its behavior:

- `tp/attacks.py`
- `tp/provenance.py`
- Copied portions of `tp/sentinel_live.py`

Only the imports and other strictly necessary compatibility adjustments may be changed.

- Do not modify `legacy/tp_lib.py`.
- Do not silently change algorithms, thresholds, return values, or verification behavior.
- Document every divergence and its justification in `DEVELOPMENT_LOGS.md`.
- Add regression tests for copied behavior.

### 5.4. Streamlit State Management

Streamlit reruns the application script after user interactions.

- Call `Ground.verify` from a button-triggered processing action.
- Verify each received packet exactly once per processing operation.
- Store the relevant processing state in `st.session_state`.
- Do not accidentally verify the same packet again because of a rerun.
- Preserve replay-detection semantics and test them explicitly.

### 5.5. Offline Mode

Always provide an offline mode using `samples/`.

- The application must remain usable when network access fails.
- Handle timeouts, HTTP 403 and 429 responses, and other network errors gracefully.
- Display a clear offline-mode warning when falling back to local samples.
- Never claim that live Copernicus data was retrieved if the request failed.
- Keep the online and offline processing paths consistent with the model input contract.

### 5.6. Testing

- Add `pytest` tests for every module.
- Test successful behavior, invalid inputs, error handling, and relevant security properties.
- Add regression tests for legacy behavior.
- Use network tests only when appropriate and skip them explicitly when network access is unavailable.
- Run the required test suite before declaring a step `DONE`.
- Never fabricate test results, benchmark measurements, or validation outcomes.

### 5.7. Dependency Management

Pin all dependency versions in `requirements.txt`.

- Avoid unnecessary dependencies.
- Do not add PyTorch to the deployed runtime.
- Verify that the pinned dependencies are compatible with the selected Python version and deployment platform.

## 6. Language

- All UI text, code comments, docstrings, `DEVELOPMENT_LOGS.md` entries, commit messages, README files, reports, and test names that we create or modify must be in **English**.
- **Exception:** Functions copied verbatim from `legacy/tp_lib.py` in `tp/attacks.py`, `tp/provenance.py`, and copied portions of `tp/sentinel_live.py` must preserve their original French strings and comments.
- Verification messages returned by copied legacy functions, including messages such as `"signature invalide : ..."`, must be displayed exactly as returned. Do not add a translation layer or rewrite these messages.
- Do not create `tp/i18n.py`.
- Messages introduced by our own code in the engine, API, and UI must be in English.
- Status names must remain exactly `TRUSTED`, `SUSPICIOUS`, and `COMPROMISED`.
- Development log status values must remain exactly `DONE`, `PARTIAL`, and `BLOCKED`.
- When checking for French text, allow only the explicitly documented legacy-code exceptions. All other French text in files created or modified by us must be corrected.

## 7. Environment and Execution

- Operating system: Windows.
- Shell: PowerShell.
- Use the existing virtual environment without requiring activation.
- Always execute Python commands through:

  ```powershell
  .\.venv\Scripts\python.exe -m <module>
  ```

- Do not assume that the virtual environment, scripts, or dependencies exist without checking.
- Use relative paths in commands, logs, documentation, and generated files whenever possible.

### Model Hosting

The model is hosted in the following public Hugging Face repository:

`trustthepixel/trust-the-pixel-detector`

Reference it through the `HF_MODEL_REPO` environment variable where required.

Do not hardcode credentials or access tokens. Do not assume that the model can be downloaded if network access is unavailable.

### Deployment

Deploy through **Streamlit Community Cloud connected to GitHub**.

Hugging Face Streamlit Spaces are paid for this project and must not be used.

Do not change the deployment target without explicit user authorization.

### Anonymity

Never include any of the following in repository files, logs, reports, or commit messages:

- Absolute file paths
- Personal usernames
- Email addresses
- Kaggle usernames
- Real names
- Secrets or access tokens

Use relative paths only. Avoid exposing personal information in stack traces, generated reports, screenshots, or documentation.

### Network Restrictions

If network access is blocked by the sandbox:

1. Record the limitation in `DEVELOPMENT_LOGS.md`.
2. Do not invent successful downloads, API responses, deployment results, or network-test outcomes.
3. Provide the exact command the user must execute manually.
4. Mark the step `PARTIAL` or `BLOCKED`, depending on whether the remaining work can proceed without network access.

## 8. Resume Prompt

If Codex stops unexpectedly or loses context, use the following instructions:

```text
Read AGENTS.md and DEVELOPMENT_LOGS.md.

Resume exactly at the last PARTIAL or BLOCKED entry. If neither exists, continue with the next announced step.

Do not redo work already marked DONE.

First, append an entry to DEVELOPMENT_LOGS.md identifying the step being resumed, its current status, the exact stopping point, and the next actions.

Inspect the relevant files and existing test results before making changes. Continue from the recorded state, preserving all project rules.

At the end, follow the mandatory end-of-step procedure in AGENTS.md.
```

## 9. End-of-Step Check Prompt

Use this prompt whenever an implementation step appears incomplete or questionable:

```text
End-of-step check.

1. Reread DEVELOPMENT_LOGS.md and confirm that the current step's entry exists, uses exactly DONE, PARTIAL, or BLOCKED, and accurately reflects the work performed.

2. Run .\scripts\check.ps1 and report the actual output. Do not fabricate successful results. If the script does not exist, explain why and follow the initial setup exception.

3. List the gaps between the original step requirements and the implementation. Distinguish completed work, incomplete work, untested behavior, and blockers.

4. Verify that no absolute path, real name, username, email address, secret, or prohibited file from model/, docs/, legacy/, data_raw/, keys/, *.pem, .env, or .leakwords is tracked by Git.

5. Check that all files created or modified by us contain English text, including comments, docstrings, UI text, tests, reports, README files, and development log entries. Preserve the explicitly permitted French strings and comments in verbatim legacy-derived code. Do not introduce a translation layer or modify legacy messages.

6. Fix all issues that can safely be fixed without violating project rules. Rerun the relevant checks.

7. Update DEVELOPMENT_LOGS.md with the actual outcome and any remaining gaps.

8. Review the final log entry before declaring the step DONE.

9. Follow the mandatory end-of-step procedure, including Git commit and push, subject to the documented authentication and initial setup exceptions.
```

## 10. Golden Rule

**One prompt at a time.**

After each prompt:

1. Inspect the implementation and relevant tests.
2. Read the latest entry in `DEVELOPMENT_LOGS.md`.
3. Verify that the recorded status matches the actual result.
4. Complete the end-of-step checks.
5. Commit and push according to the mandatory procedure.

Never skip the development log, never claim unverified results, never silently redo work marked `DONE`, and never weaken the project's security or model input requirements to make a test pass.
## Dashboard v2 (single-page map dashboard)
- The dashboard is ONE page: a full-height map on the right and a left control panel (st.sidebar). No multipage navigation and no extra pages.
- Two modes selected at the top of the panel: "Analyze area" and "Live monitor".
- The analysis area has a FIXED size: 256x256 pixels at 10 m (2.56 km x 2.56 km), the model's training input. Never resize or stitch.
- Keep tp/, api.py, attacker/ and their tests. Remove every feature that is not part of the two modes.
- Step numbering continues: P12 ... P18.
- UI texts stay in English. Basemap tiles come from the internet; provide an offline fallback (no tiles).
