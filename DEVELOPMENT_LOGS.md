# Development Logs

## [2026-10-27 20:47] Step P-1.0: Prepare Python environment and generate offline samples
- Status: COMPLETED
- Files created or modified: `.gitignore`, `scripts/make_samples.py`, `samples/chip_*.npy`, `samples/chip_*.json`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Created `.venv` using Python 3.12.10 and upgraded pip.
  - Installed NumPy and pandas in the virtual environment.
  - Added required ignore patterns without removing any existing lines; `.gitignore` did not exist.
  - Added a sample generator with input shape, dtype, length, required metadata, and output checks.
  - Generated and reloaded 25 samples; all arrays have shape `(4, 256, 256)` and dtype `uint16`, and all JSON files contain the required keys.
  - Selected 6 cloudy samples. No non-sample files were present in `samples/` before generation, so none were deleted.
- Commands executed and test results: `py -3.12 -m venv .venv` (success); `\.venv\Scripts\python.exe -m pip install --upgrade pip` (success); `\.venv\Scripts\python.exe -m pip install numpy pandas` (success); `\.venv\Scripts\python.exe -m scripts.make_samples` (success: 25 chips verified, 6 cloudy).
- Decisions and assumptions: Region selection matches case-insensitive region names containing `tunis` or `beja` (including Beja variants). Regular interval selection uses `max(1, N // 15)`. No Git operations were run, as requested.
- Remaining work / exact stopping point: P-1.0 is complete. No Git operations were run.

## [2026-10-27 20:54] Step P-1: Initialize Git and set up guardrails
- Status: DONE
- Files created or modified: `scripts/check_leaks.py`, `scripts/check_language.py`, `scripts/check.ps1`, `scripts/install_hooks.ps1`, `tests/test_leaks.py`, `tests/test_language.py`, `DEVELOPMENT_LOGS.md`, `.git/config`, `.git/hooks/pre-commit`.
- Summary of work completed (3-8 lines):
  - Initialized Git on `main`, configured the requested local author identity, and set the `origin` URL using the public account ID.
  - Added a tracked and staged file leak scanner, an authored text language scanner, the consolidated check script, and the pre-commit hook.
  - Added temporary repository regression tests for allowed and forbidden content, protected paths, staged content, language detection, and the allow-list marker.
  - Installed and ran the pre-commit hook. It passed.
  - Corrected the accented region spelling in the earlier log entry to satisfy the English language guard.
  - Reworked a test fixture after the staged leak check detected the forbidden pattern in test source; the fixture still exercises the detection at runtime.
  - `git add -n .` listed no files from `model/`, `docs/`, `legacy/`, or `data_raw/`.
- Commands executed and test results: GitHub public user API returned the account ID; `git config --local --list` showed the requested local identity and remote; `\.venv\Scripts\python.exe -m pytest -q` passed 14 tests; after correcting the test fixture, the staged `\.\scripts\check.ps1` passed with `CHECK OK`; dry-run staging excluded all prohibited data directories.
- Decisions and assumptions: Git identity and remote settings are local only. No global configuration was read or changed. No push was run.
- Remaining work / exact stopping point: No remaining P-1 work after the requested initial commit and author verification.

## [2026-10-27 21:09] Step P0: Create project scaffolding and audit the implementation guide
- Status: DONE
- Files created or modified: `tp/__init__.py`, `dashboard_pages/.gitkeep`, `assets/.gitkeep`, `attacker/.gitkeep`, `.streamlit/config.toml`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `tests/test_assets.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Created the requested package and workspace folders, a dark Streamlit theme, and a registered `network` pytest marker.
  - Installed the requested app and API packages on Python 3.12.10, then pinned the resolved versions of all 22 runtime packages.
  - Kept Torch and segmentation-models-pytorch out of both dependency files.
  - Added artifact checks for sample pairs, metadata, model configuration, golden data, and ONNX Runtime loading.
  - Confirmed all requested model files exist and all 25 sample arrays have paired metadata; no requested artifact or sample pair is missing.
- Audit of `docs/` and `legacy/tp_lib.py`:
  - a) Correct in the monolithic file: the provenance section uses `ALL_FAMILIES`, `SEV_ALL`, and `make_attack` defined in the attack section. When split, provenance should import these from `tp.attacks`; attacks must not import provenance, avoiding a cycle.
  - b) Inconsistent: `channel_attack` and the dashboard selector use `manifest_rehash`, while the mitmproxy addon and scenario `EXPECT` use `rehash`. Standardize on `manifest_rehash` in the addon and scenario table, or add an explicit boundary alias while leaving legacy behavior unchanged.
  - c) The 8.4 excerpt relies on `TRUSTED_KEYS` loaded in 8.3. Sequential execution works, but the excerpt is not standalone. Import an explicit key loader or configuration object in the API module and fail closed when no keys are provisioned.
  - d) Confirmed for resolved Streamlit 1.66.1: `st.image(..., use_container_width=True)` is deprecated in current documentation. Use `width="stretch"` for the same layout.
  - e) `Source.acquire` reads `date`, `lon`, `lat`, `scene`, `tile`, `r0`, `c0`, and `offset`. The 25 generated sample sidecars include every field. The guide refers to `sample_scene` from notebook 06 but does not include its implementation, so its emitted metadata could not be confirmed here. Add an explicit required-key check at that boundary; avoid silent defaults for missing fields.
  - f) Correct: `tile_hashes` iterates y outside x, producing row-major indices. A 256 by 256 chip with 32-pixel tiles has 8 rows, 8 columns, and 64 leaves. Preserve this ordering when mapping changed indices to the image.
  - g) Correct for the fixed 256 by 256 output: Torch selects the top 200 logits and NumPy sorts and averages the final 200. They select the same values; reduction order can cause negligible floating-point differences. Keep both implementations at k=200 and test their tolerance.
  - h) Preserve these legacy strings exactly if shown in the UI or parameter report; do not translate or normalize them: `paquet incomplet (manifeste ou pixels absents)`; `signature absente : origine non vérifiable`; `clé inconnue ({kid}) : signataire non reconnu`; `signature invalide : manifeste modifié ou signé par un tiers`; `empreinte SHA-256 différente : pixels modifiés après la signature`; `rejeu : nonce déjà vu ou compteur non croissant`; `capteur non autorisé`; `date d'acquisition dans le futur`; `date d'acquisition illisible`; `position hors des zones attendues`; `anomalie de contenu forte (score {score:.2f} ≥ {t_high:.2f})`; `origine non vérifiée`; `anomalie de contenu (score {score:.2f} ≥ {t_low:.2f})`. # lang-ok
  - h) Legacy attack records also expose French parameter names and labels: `classe`, `facteur`, `qualite`, `n_objets`, `rayon`, `bande`, `flou`, `nettete`, and the note `attaque imperceptible rejetée`. # lang-ok
  - i) Additional risks: the guide's Hugging Face Streamlit Space conflicts with the project rule to deploy on Streamlit Community Cloud; docs refer to `dashboard/app.py` while this task creates `dashboard_pages/`; `Source.acquire` casts to uint16 and defaults missing metadata instead of enforcing the input contract; the API excerpt has no payload-size guard and malformed manifests can raise uncaught errors; replay memory resets when the API restarts; Copernicus imagery is unsigned and the guide's source signature is simulated. Keep the ONNX runtime separate from the legacy module's top-level Torch imports and retain the offline sample path.
- Commands executed and test results: `\.venv\Scripts\python.exe -m pip install -r requirements.txt` succeeded; the pinned reinstall succeeded; `\.venv\Scripts\python.exe -m pip check` reported no broken requirements; `\.venv\Scripts\python.exe -m scripts.make_samples` verified 25 chips and 6 cloudy chips; `\.venv\Scripts\python.exe -m pytest -q` passed 16 tests, including ONNX session loading and sample metadata checks.
- Decisions and assumptions: Pins are the exact Windows Python 3.12 resolutions and all requested direct packages are cross-platform distribution names; Linux installation was not run in this Windows workspace. No edits were made under `legacy/`, `model/`, or `data_raw/`; none of those directories will be staged.
- Remaining work / exact stopping point: No implementation work remains. The final check passed; the required Git commit and push are the last actions for P0.

## [2026-10-27 21:11] Step P0 follow-up: Record the remote push result
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Created local commit `P0: Create project scaffolding` after the staged guardrails passed.
  - The initial `git push` reported that `main` has no upstream; `git push -u origin main` then returned `Repository not found`.
  - The configured origin matches the requested GitHub URL, but that remote is not currently reachable as a repository with this access.
  - No credentials or remote settings were changed.
- Commands executed and test results: `git push` (no upstream configured); `git push -u origin main` (failed: remote repository not found).
- Decisions and assumptions: Treat the remote result as a blocker requiring confirmation that the requested repository exists and is accessible. Do not create a repository or alter the specified origin without instruction.
- Remaining work / exact stopping point: After confirming the repository URL and access, run `git push -u origin main` manually.

## [2026-10-27 21:22] Step P0 follow-up: Publish under the pseudonymous account
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Confirmed GitHub CLI is authenticated as `trustthepixel` and that account is active.
  - Confirmed the local `main` branch is clean, `origin` targets `trustthepixel/trust-the-pixel`, and the local commit author uses `tp-team` with the `trustthepixel` noreply address.
  - The earlier push attempt did not create a remote repository or publish any commits.
- Commands executed and test results: `gh auth status` confirmed `trustthepixel` active; `git status --short` clean; `git remote -v` confirmed the expected remote; `git log -1` confirmed the pseudonymous commit author.
- Decisions and assumptions: Create the GitHub repository as private because public visibility was not requested; preserve all existing local commits and files.
- Remaining work / exact stopping point: Run the project checks, commit this log update, create the remote repository under `trustthepixel`, then push `main`.

## [2026-10-27 21:23] Step P0 follow-up: Publish under the pseudonymous account
- Status: COMPLETED
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Created the private GitHub repository `trustthepixel/trust-the-pixel` while GitHub CLI was authenticated as `trustthepixel`.
  - Pushed the local `main` branch and configured it to track `origin/main`.
  - Kept the local commit identity pseudonymous as `tp-team` with the account's GitHub noreply address.
  - No files under `model/`, `docs/`, `legacy/`, or `data_raw/` were added by this follow-up.
- Commands executed and test results: `gh repo create trustthepixel/trust-the-pixel --private` succeeded; `git push -u origin main` succeeded; `scripts/check.ps1` passed (16 tests, leak check, language check).
- Decisions and assumptions: Repository visibility is private; the user can change visibility later from GitHub settings if desired.
- Remaining work / exact stopping point: No work remains for this step.

## [2026-10-27 21:29] Step P1: Split legacy runtime modules
- Status: PARTIAL
- Files created or modified: `tp/attacks.py`, `tp/provenance.py`, `tp/data_io.py`, `tests/test_split.py`, `tests/test_attacks.py`, `tests/test_provenance.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Extracted attack generation, provenance and audit-log logic, and GeoTIFF export into the requested light modules.
  - Kept the copied functions and classes AST-equivalent to `legacy/tp_lib.py`; only module imports and the nonfunctional GeoTIFF comment differ.
  - Added regression coverage for AST parity, sample verification, channel attacks, attack families, audit-log tampering, and imports without PyTorch.
  - Confirmed the focused regression set passes: 15 tests.
- Commands executed and test results: `\.venv\Scripts\python.exe -m pytest tests/test_split.py tests/test_attacks.py tests/test_provenance.py -q` � 15 passed; `git diff --check` � clean.
- Decisions and assumptions: Keep French legacy text in the verbatim copied modules; `rasterio` remains imported inside `export_geotiff`.
- Remaining work / exact stopping point: Run the complete check suite, stage and inspect changes, commit, and push to `origin/main`.

## [2026-10-27 21:30] Step P1: Split legacy runtime modules
- Status: DONE
- Files created or modified: `tp/attacks.py`, `tp/provenance.py`, `tp/data_io.py`, `tests/test_split.py`, `tests/test_attacks.py`, `tests/test_provenance.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Split the requested attack, provenance, audit-log, and GeoTIFF export code into lightweight runtime modules.
  - AST regression checks confirm the copied functions, classes, and requested constants match the legacy source; imports and the GeoTIFF comment are the only differences.
  - Tests cover all sample packets, every channel attack, all 17 attack families, audit-log tampering and unanchored truncation, and no-PyTorch imports.
  - The complete suite passes, and the implementation commit was pushed to `origin/main`.
- Commands executed and test results: `\.\scripts\check.ps1` � 31 passed, leak check passed, language check passed, `CHECK OK`; `git commit` and `git push` succeeded.
- Decisions and assumptions: Keep legacy French strings and comments verbatim in `tp/attacks.py` and `tp/provenance.py`; keep `rasterio` imported inside `export_geotiff`.
- Remaining work / exact stopping point: No remaining work for P1.

## [2026-10-27 21:31] Step P1 follow-up: Correct the recorded check command
- Status: DONE
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Clarified a command formatting typo in the preceding P1 completion entry.
  - The command executed was `\.\scripts\check.ps1` (PowerShell), not the malformed command string shown in that entry.
  - The P1 modules and tests are unchanged.
- Commands executed and test results: `\.\scripts\check.ps1` � 31 passed, leak check passed, language check passed, `CHECK OK`.
- Decisions and assumptions: Preserve the earlier log entry and append this correction as required by the append-only log rule.
- Remaining work / exact stopping point: Commit and push this log correction.

## [2026-10-27 21:32] Step P1 follow-up: Finalize the logged check command
- Status: DONE
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Superseded the two preceding command-format corrections with this exact command record.
  - The required PowerShell check command is `.\\scripts\\check.ps1`.
  - No implementation files changed.
- Commands executed and test results: `.\\scripts\\check.ps1` � 31 passed, leak check passed, language check passed, `CHECK OK`.
- Decisions and assumptions: Keep the development log append-only and retain the prior entries for traceability.
- Remaining work / exact stopping point: No remaining work for P1.

## [2026-10-27 21:33] Step P1 follow-up: Record the exact check path
- Status: DONE
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - This entry supersedes preceding formatting corrections and records the check path with single Windows separators.
  - The P1 implementation and test results remain unchanged.
- Commands executed and test results: .\scripts\check.ps1 � 31 passed, leak check passed, language check passed, `CHECK OK`.
- Decisions and assumptions: Preserve prior entries and append this clarification.
- Remaining work / exact stopping point: No remaining work for P1.

## [2026-10-27 21:35] Step P2: Add ONNX inference and golden self-test
- Status: PARTIAL
- Files created or modified: `tp/onnx_analyzer.py`, `tp/selftest.py`, `tests/test_onnx.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Added CPU-only ONNX inference with input validation, calibration checks, batched analysis, confidence scoring, and model version metadata.
  - Added `python -m tp.selftest` to compare golden chip scores and probability maps.
  - Golden self-test passed for 12 chips: maximum score difference 0.00000706 and maximum probability difference 0.00001633.
  - The 20-run single-chip analyzer latency measurement was 399.388 ms on this environment.
- Commands executed and test results: `\.venv\Scripts\python.exe -m pytest tests/test_onnx.py -q -s` � 6 passed; `\.venv\Scripts\python.exe -m tp.selftest` � `ok: true`, `n: 12`.
- Decisions and assumptions: Valid offsets accept integer or floating-point 0/1000 values because the golden archive stores offsets as floats; no additional normalization is applied.
- Remaining work / exact stopping point: Stage the changes, run the complete project check, then commit and push.

## [2026-10-27 21:36] Step P2: Add ONNX inference and golden self-test
- Status: DONE
- Files created or modified: `tp/onnx_analyzer.py`, `tp/selftest.py`, `tests/test_onnx.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - Implemented CPU-only ONNX inference, calibration validation, strict dynamic input contract checks, single and batched analysis, trust scoring, and version metadata.
  - Added the JSON-producing self-test command and verified all 12 golden chips.
  - Golden comparison passed with maximum score difference 0.00000706 and maximum probability difference 0.00001633.
  - Recorded the 20-run mean single-chip latency: 399.388 ms.
  - Committed and pushed the implementation to `origin/main`.
- Commands executed and test results: `tp.selftest` reported `ok: true`; `tests/test_onnx.py` passed 6 tests; `scripts/check.ps1` passed 37 tests, leak check, and language check (`CHECK OK`); commit and push succeeded.
- Decisions and assumptions: Accept offsets represented as integer or floating-point 0/1000 values; no additional normalization is applied. The golden artifact was present, so tests ran rather than skipping.
- Remaining work / exact stopping point: No remaining work for P2.

## [2026-10-27 21:37] Step P2 follow-up: Record the log push blocker
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - The ONNX implementation commit `9bc56d7` was pushed to `origin/main`.
  - The final P2 results log commit was created locally, but its push failed because DNS resolution for `github.com` failed.
  - The full check suite passed before that push attempt: 37 tests, leak check, and language check.
- Commands executed and test results: `git push` failed with `Could not resolve host: github.com`; retrying after committing this blocker record.
- Decisions and assumptions: Treat the push failure as a network blocker and preserve the local commit; do not alter credentials or remote configuration.
- Remaining work / exact stopping point: Commit this blocker record and retry `git push`; if it still fails, run `git push` manually when network access is available.

## [2026-10-27 21:38] Step P2 follow-up: Resolve the remote push blocker
- Status: DONE
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3-8 lines):
  - A retry of `git push` succeeded after the earlier DNS failure.
  - The P2 implementation and all P2 log entries are now published to `origin/main`.
  - The local branch is synchronized with the remote.
- Commands executed and test results: The retry pushed commits through `2c6b21d`; the checks passed with 37 tests, leak check, and language check.
- Decisions and assumptions: No manual user action is needed for the transient network failure.
- Remaining work / exact stopping point: No remaining work for P2.

## [2026-10-27 21:54] Step P3: Validate inputs and read live Sentinel-2 chips
- Status: PARTIAL
- Files created or modified: 	p/contract.py, 	p/sentinel_live.py, 	ests/test_contract.py, scripts/live_smoke.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added chip and STAC item contract validation, including blocking tensor checks and non-blocking metadata/domain warnings.
  - Copied the six notebook 01 helper functions and required constants into 	p/sentinel_live.py; the AST equivalence regression test passes.
  - Added the requested region boxes, retry-wrapped STAC and raster reads, cloud context, same-scene chip reads, and adjacent chip grids.
  - Added marked live validation/inference coverage and a live smoke command for four regions.
  - The live request could not reach Planetary Computer; no live score table was measured.
- Commands executed and test results: .venv pytest suite — 48 passed, 1 skipped; scripts.live_smoke — network unavailable after three retries, so no live chips or scores were measured. The suite emitted one upstream Pydantic deprecation warning.
- Decisions and assumptions: Notebook helper functions remain AST-equivalent; retry handling is applied at the Planetary Computer and Rasterio boundaries. The supplied notebooks are reference inputs and were not edited. Rerun live sampling with \.\.venv\Scripts\python.exe -m scripts.live_smoke when network access is available.
- Remaining work / exact stopping point: Run the mandatory project check and Git end-of-step procedure; live measurements remain unavailable until Planetary Computer can be reached.

## [2026-10-27 21:57] Step P3 follow-up: Exclude notebook reference outputs
- Status: PARTIAL
- Files created or modified: .gitignore, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The staged leak check found a Kaggle dataset path in the supplied 	raining.ipynb notebook output.
  - Kept both supplied notebooks unchanged and excluded them from Git; the reference files remain in the workspace.
  - The P3 implementation, tests, live smoke script, and log remain staged for the guarded project commit.
  - Live Planetary Computer access was unavailable, so the requested live score table remains unmeasured.
- Commands executed and test results: Staged scripts/check.ps1 reported 49 passed, leak check failed on 	raining.ipynb, and language check passed. The notebook was removed from the index without changing its workspace copy; both notebook filenames are now ignored.
- Decisions and assumptions: Reference notebook outputs are excluded because the leak guard correctly rejects their embedded Kaggle dataset path. The exact retry command remains \.\.venv\Scripts\python.exe -m scripts.live_smoke.
- Remaining work / exact stopping point: Rerun the full check against the safe staged set, then commit and push if green. Live smoke must be rerun when network access is available.

## [2026-10-27 21:58] Step P3 follow-up: Complete guarded checks
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Excluded the unmodified notebook reference artifacts from the staged project files after the leak guard identified an embedded Kaggle dataset path.
  - The full project check now passes on the safe staged set: 48 tests passed, one network test skipped, leak check passed, and language check passed.
  - The network test skip reflects the unavailable Planetary Computer service; live chips and scores remain unmeasured.
- Commands executed and test results: \.\scripts\check.ps1 — CHECK OK; 48 passed, 1 skipped, leak and language checks passed.
- Decisions and assumptions: Keep the task PARTIAL until live sampling is available, as required by the network restriction rule.
- Remaining work / exact stopping point: Stage this final log entry, rerun \.\scripts\check.ps1, then commit and push the verified changes.

## [2026-10-27 21:59] Step P3 follow-up: Clarify the manual retry command
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Clarified the exact manual live smoke command after path escaping affected its display in an earlier log entry.
  - The local reference artifact excluded by the staged leak guard is 	raining.ipynb; neither supplied notebook was modified.
- Commands executed and test results: The final staged check immediately before this note passed: 48 passed, 1 skipped, leak check passed, language check passed (CHECK OK).
- Decisions and assumptions: The exact manual command is . + '\' + .venv + '\' + Scripts + '\' + python.exe -m scripts.live_smoke; network access remains unavailable.
- Remaining work / exact stopping point: Stage this note, run the final check, then commit and push the guarded changes.

## [2026-10-27 22:00] Step P3 follow-up: Record the literal retry command
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The exact manual command for retrying the live smoke check is recorded below.
  - The supplied notebook references remain unchanged and excluded from the commit.
- Commands executed and test results: The latest full check passed with 48 tests passed, one network test skipped, and leak and language checks passed.
- Decisions and assumptions: Network availability is still required to measure live chip scores.
- Remaining work / exact stopping point: Stage the log update, run the final check, commit and push. Retry live sampling with:
  .\.venv\Scripts\python.exe -m scripts.live_smoke

## [2026-10-27 22:01] Step P3 follow-up: Publish the guarded implementation
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The P3 implementation and guardrails were committed as a7c5eaf and pushed to origin/main.
  - The full check passed before the implementation commit: 48 tests passed, one network test skipped, and leak and language checks passed.
  - Live Planetary Computer chips and scores remain unmeasured because the network request was unavailable.
- Commands executed and test results: git commit succeeded; git push succeeded from main to origin/main.
- Decisions and assumptions: Keep the P3 status PARTIAL until network access allows the live chip smoke to run.
- Remaining work / exact stopping point: Run the final check after this log update, then commit and push this record. Retry live sampling with:
  .\.venv\Scripts\python.exe -m scripts.live_smoke

## [2026-10-27 22:03] Step P3 follow-up: Expand and report live smoke behavior
- Status: PARTIAL
- Files created or modified: scripts/live_smoke.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Updated the smoke command to search recent scenes across Tunis, Kairouan, Sfax, and Gabes and score up to 10 clean chips.
  - The final project check before this update reported 49 passed, including the marked Tunis live validation test.
  - Standalone smoke attempts still failed at the STAC request after three retries, so no reproducible region score table was available.
- Commands executed and test results: The smoke command returned NetworkUnavailable (APIError) and printed the rerun command. One full pytest run reported 49 passed with no skips; prior runs skipped the network case when Planetary Computer was unavailable.
- Decisions and assumptions: Keep the task PARTIAL because no stable smoke table was measured. Retry with the exact command below when network access is stable:
  .\.venv\Scripts\python.exe -m scripts.live_smoke
- Remaining work / exact stopping point: Run the final project check, commit, and push this smoke-script and log update.

## [2026-10-27 22:05] Step P3 follow-up: Verify final smoke implementation
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The expanded smoke script and all P3 implementation files passed the full project check.
  - The latest check reported 48 passed and one network test skipped; leak and language checks passed.
  - The independent Tunis live validation had passed in an earlier run, but live access was intermittent and smoke could not produce the requested table.
- Commands executed and test results: .\scripts\check.ps1 — CHECK OK; 48 passed, 1 skipped, leak check passed, language check passed.
- Decisions and assumptions: Live score table remains unmeasured; the exact smoke command is provided in the preceding entry.
- Remaining work / exact stopping point: Stage this result, run the check once more, then commit and push.

## [2026-10-27 22:08] Step P3 follow-up: Bound STAC offline waits
- Status: PARTIAL
- Files created or modified: tp/sentinel_live.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - A final check attempt was interrupted after the offline STAC call exceeded the observed retry window.
  - Added a 10-second pystac-client request timeout and disabled its internal retry loop so the required outer retry wrapper controls attempts.
  - The expanded smoke script remains configured to inspect recent scenes and score up to 10 clean chips.
- Commands executed and test results: The interrupted .\scripts\check.ps1 run did not produce a test result. A new full check is required after this timeout change.
- Decisions and assumptions: Three outer attempts remain, with exponential backoff; on offline service failures the network test should skip after bounded waits.
- Remaining work / exact stopping point: Run .\scripts\check.ps1, update this log with its result if needed, then commit and push.

## [2026-10-27 22:11] Step P3 follow-up: Complete live validation
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added bounded STAC request timeouts, retained three outer retries, and expanded the smoke script to gather up to 10 recent clean chips.
  - The project check passed with 49 tests, leak check, and language check; the marked live Tunis validation ran successfully.
  - Live smoke retrieved and scored 10 clean chips. All measured scores were below t_low.
- Commands executed and test results: .\scripts\check.ps1 — CHECK OK, 49 passed, leak and language checks passed. .\.venv\Scripts\python.exe -m scripts.live_smoke — 10 chips scored.
- Decisions and assumptions: The unmodified reference notebooks remain excluded from Git because the training notebook output contains a Kaggle dataset path. Network access recovered for the final smoke run.
- Live smoke results:
  | Region | Scene | Date | Offset | Score | Compared with t_low |
  | --- | --- | --- | ---: | ---: | --- |
  | Tunis | S2A_MSIL2A_20261026T101031_R022_T32SPG_20261026T165007 | 2026-10-26 | 1000 | -1.531600 | below |
  | Tunis | S2A_MSIL2A_20261023T100041_R122_T32SPG_20261023T163256 | 2026-10-23 | 1000 | -1.831180 | below |
  | Tunis | S2A_MSIL2A_20261023T100041_R122_T32SPF_20261023T163256 | 2026-10-23 | 1000 | -1.468305 | below |
  | Tunis | S2A_MSIL2A_20261023T100041_R122_T32SNG_20261023T163256 | 2026-10-23 | 1000 | -2.068196 | below |
  | Tunis | S2A_MSIL2A_20261023T100041_R122_T32SNF_20261023T163256 | 2026-10-23 | 1000 | -1.851773 | below |
  | Tunis | S2C_MSIL2A_20261021T100041_R122_T32SNF_20261021T140303 | 2026-10-21 | 1000 | -1.691883 | below |
  | Tunis | S2B_MSIL2A_20261019T101029_R022_T32SPG_20261019T140547 | 2026-10-19 | 1000 | -1.545304 | below |
  | Tunis | S2B_MSIL2A_20261019T101029_R022_T32SNG_20261019T140547 | 2026-10-19 | 1000 | -1.969441 | below |
  | Tunis | S2A_MSIL2A_20261016T101041_R022_T32SPG_20261016T170806 | 2026-10-16 | 1000 | -1.634591 | below |
  | Kairouan | S2A_MSIL2A_20261026T101031_R022_T32SNE_20261026T165007 | 2026-10-26 | 1000 | -1.469888 | below |
- Remaining work / exact stopping point: Run the final check after this log update, commit, and push.

## [2026-10-27 22:20] Step P4: Add the trust pipeline
- Status: PARTIAL
- Files created or modified: tp/engine.py, tests/test_engine.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added TrustPipeline construction with a demo signing source, pinned public key, widened regional AOI, and chained audit log.
  - Added single-verification packet processing, tolerant contract validation, ONNX decisions, cloud-only AI downgrade, conflict detection, and JSON-safe results.
  - Added privacy-conscious report generation with UTC timestamp and self-excluding SHA-256.
  - Added tests for all channel attacks, authentic chips, signed pre-tampering conflict, cloud cap, replay behavior, malformed input, and report hashing.
  - Left tp/provenance.py and decide unchanged.
- Commands executed and test results: Focused engine tests — 12 passed; full project check not yet run.
- Decisions and assumptions: Conflict means valid provenance and integrity with model score at or above t_low. Only an AI-only COMPROMISED result is eligible for cloud downgrade.
- Remaining work / exact stopping point: Run .\scripts\check.ps1; fix any issues, then stage, commit, and push.

## [2026-10-27 22:21] Step P4 follow-up: Verify full pipeline checks
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The full project check passed with all 61 tests passing.
  - Leak and language checks passed.
  - The focused integration tests confirmed expected attack handling, exactly-once verification per call, replay detection on the second call, cloud cap behavior, and report hashing.
  - tp/provenance.py and decide were not modified.
- Commands executed and test results: .\scripts\check.ps1 — CHECK OK; 61 passed, leak check passed, language check passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: Mark P4 DONE based on the passing full suite and security/language checks.
- Remaining work / exact stopping point: Stage this log entry, run the final check, then commit and push.

## [2026-10-27 22:26] Step P5: Build the dashboard shell and visual identity
- Status: PARTIAL
- Files created or modified: app.py, assets/style.css, assets/logo.svg, dashboard_pages/*.py, .streamlit/config.toml, tests/test_app_smoke.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added the dark mission-control theme, reusable CSS components, logo, and 13-page sidebar navigation.
  - Added one render(ctx) entry point per page; pages 1-12 are placeholders and page 13 contains the Model Card.
  - Added cached shared runtime setup, per-session state keys, optional model preparation, self-test reporting, and read-only startup failure behavior.
  - Added documented per-family AUCs, reported confidence intervals, thresholds, hashes, self-test status, and limitations.
  - AppTest confirms startup, Model Card rendering, permanent signature notice, and compatible image sizing.
- Commands executed and test results: Focused AppTest — 2 passed. Full project check not yet run.
- Decisions and assumptions: Documentation part 4 provides 95% intervals only for copy_move and photometric; other intervals are labeled Not reported and are not fabricated.
- Remaining work / exact stopping point: Run .\scripts\check.ps1; fix any issues, then stage, commit, and push.

## [2026-10-27 22:27] Step P5 follow-up: Verify dashboard checks
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The full project check passed with all 63 tests passing.
  - Leak and language checks passed.
  - AppTest verified the application starts, the permanent simulated-signature notice appears, and the Model Card page renders.
  - Streamlit accepted the numeric image width and the Model Card uses width='stretch' for its chart.
- Commands executed and test results: .\scripts\check.ps1 — CHECK OK; 63 passed, leak check passed, language check passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: Unreported AUC confidence intervals remain labeled Not reported.
- Remaining work / exact stopping point: Stage this result, run the final check, then commit and push.

## [2026-10-27 22:34] Step P6: Implement acquisition, mission control, and map pages
- Status: PARTIAL
- Files created or modified: app.py, assets/style.css, dashboard_pages/copernicus_acquisition.py, dashboard_pages/page_01_mission_control.py, dashboard_pages/page_03_map.py, tp/sentinel_live.py, tests/test_app_smoke.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Added live and local sample acquisition controls, validation checks, scene metadata, RGB preview, and per-band histograms.
  - Added automatic local-sample fallback with persistent offline banner and cache for live chip queries.
  - Added Mission Control packet signing, attack selection, exactly-once processing guard, status, evidence, reasons, latency, and trust gauge.
  - Added a map with region polygons and a status-colored chip marker, plus a built-in map fallback.
  - Added an AppTest for the complete offline acquisition and analysis flow, including the disabled second-send state.
- Commands executed and test results: Focused AppTest: 3 passed. Full project check is pending.
- Decisions and assumptions: Offline mode remains session-scoped; the global sidebar toggle and acquisition fallback keep it visible across page navigation. Cached live requests use a 10-minute TTL.
- Remaining work / exact stopping point: Run scripts/check.ps1, resolve any failures, append final check results, then commit and push.
## [2026-10-27 22:36] Step P6 follow-up: Verify acquisition and mission-control pages
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - The offline acquisition-to-analysis AppTest passed and confirmed the second send is disabled for the already analyzed observation.
  - The automatic network fallback synchronizes the offline toggle before Streamlit creates its widget, keeping the offline banner visible across pages.
  - The full test suite passed: 64 tests.
  - Leak and language checks both passed.
- Commands executed and test results: `scripts/check.ps1` — CHECK OK; 64 passed, leak check passed, language check passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: The map uses pydeck layers where available and falls back to Streamlit's built-in map if rendering fails.
- Remaining work / exact stopping point: Reread this entry, rerun the project check against the final log, then stage, commit, and push P6.
## [2026-10-27 22:42] Step P7: Implement Attack Lab and Forensics pages
- Status: PARTIAL
- Files created or modified: app.py, dashboard_pages/page_01_mission_control.py, dashboard_pages/page_04_attack_lab.py, dashboard_pages/page_05_forensics.py, tests/test_app_smoke.py, tests/test_attack_forensics.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Added seeded attack selection for all requested packet scenarios, tampering families, and severity levels, with alternate-sample donors and a rolled-chip fallback.
  - Kept attack masks and detectability records in session state, separate from the packet passed to the analysis pipeline.
  - Added replay gating based on a previously analysed packet and a source-signed stolen-key simulation.
  - Added before/after and amplified-difference previews, probability and contour overlays, row-major tile grid, mask metrics, indices, NDVI/NDWI, logits histogram, and image fade control.
  - Added real-sample status tests for each requested scenario and AppTest coverage for both new pages.
- Commands executed and test results: Focused attack and app tests: 12 passed; AppTest rerun: 3 passed. Full project check is pending.
- Decisions and assumptions: The stolen-key scenario uses the pipeline's demonstration Source so it retains the trusted key and increases its counter. The `resign` scenario uses a throwaway Source and therefore an unknown key.
- Remaining work / exact stopping point: Run `scripts/check.ps1`, fix any failures, append final verification, then stage, commit, and push.
## [2026-10-27 22:43] Step P7 follow-up: Verify attacks and forensic views
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - All eight configured scenarios produced an allowed expected final status on real sample chips.
  - The stolen-key inpaint_ns strong case retained valid provenance and integrity and triggered conflict or an AI compromise.
  - AppTest rendered Attack Lab and Forensics after the full offline acquisition and analysis flow.
  - The complete project suite passed: 73 tests; leak and language checks passed.
- Commands executed and test results: `scripts/check.ps1` — CHECK OK; 73 passed, leak check passed, language check passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: Tile highlighting uses only Ground's `changed_tiles`; the valid stolen-key case does not claim a provenance-detected tile change.
- Remaining work / exact stopping point: Reread the P7 log entry, rerun checks with the final log, then commit and push.
## [2026-10-27 22:52] Step P8: Implement Zone Scan, Archive, Audit, Report, Batch, and Upload pages
- Status: PARTIAL
- Files created or modified: app.py, dashboard_pages/_qgis.py, dashboard_pages/page_05_forensics.py, dashboard_pages/page_06_zone_scan.py, dashboard_pages/page_07_level_3_archive.py, dashboard_pages/page_08_audit_log.py, dashboard_pages/page_09_report.py, dashboard_pages/page_10_batch.py, dashboard_pages/page_11_custom_upload.py, tp/sentinel_live.py, tests/test_pages_p8.py, tests/test_offline_pages.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Added live adjacent-grid Zone Scan with batch inference and an offline sample mode that explicitly labels its chips as non-adjacent.
  - Added same-window Level 3 archive comparison, audit-chain copy simulations, JSONL/JSON/PDF downloads, local batch processing, and validated NumPy/GeoTIFF uploads.
  - Added QGIS chip and one-band predicted-mask GeoTIFF downloads to Forensics and Report, with clear missing-georeferencing messages.
  - Extended the Rasterio retry dataset wrapper to delegate context management and metadata writes so local GeoTIFF export works.
  - Added archive, audit, report, GeoTIFF, custom-upload, and offline AppTest coverage.
- Commands executed and test results: Focused P8 tests: 11 passed. Full project check is pending.
- Decisions and assumptions: Offline Zone Scan uses exactly n sample chips in an n × n display and labels the remaining layout as not a real grid. Audit tail truncation is detected against the original in-memory chain-head checkpoint because the hash-chain verify method alone cannot detect a removed tail.
- Remaining work / exact stopping point: Run `scripts/check.ps1`, fix failures, append final results, then stage, commit, and push.
## [2026-10-27 22:54] Step P8 follow-up: Verify pages and exports
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Offline Zone Scan, audit simulation, PDF/JSON report, local batch, archive refusal, and custom-upload page paths passed AppTest.
  - Simulated archive comparison, report JSON, float/shape/band-order upload refusal, and reopened four-band and one-band GeoTIFF exports passed unit tests.
  - The full project suite passed: 80 passed and one network-marked test skipped.
  - Leak and language checks passed.
- Commands executed and test results: `scripts/check.ps1` — CHECK OK; 80 passed, 1 skipped, leak check passed, language check passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: The skipped test is network-dependent; offline behavior was exercised separately by AppTest.
- Remaining work / exact stopping point: Reread this P8 entry, rerun checks with the final log, then stage, commit, and push.
## [2026-10-27 23:03] Step P9: Add the ground-station API and attack tooling
- Status: COMPLETED
- Files created or modified: .gitignore, api.py, attacker/__init__.py, attacker/README.md, attacker/mitm_addon.py, attacker/requirements.txt, attacker/run_scenarios.py, attacker/scenarios.py, attacker/source_send.py, dashboard_pages/page_12_kali_receiver.py, scripts/provision.py, tests/test_api.py, tests/test_provision.py, tp/engine.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added safe Ed25519 key provisioning with overwrite protection and owner-only private-key permissions; private key material is never printed.
  - Added a verifier-only FastAPI ground station with strict packet validation, bounded request bodies, chained in-memory audit entries, pixel-free JSONL events, health, and event endpoints.
  - Added eight pure packet scenarios, a source sender with persistent counter, a direct/proxy campaign runner, and a thin mitmproxy adapter with local mode control.
  - Implemented the local Kali Receiver view, API/provisioning tests, attacker setup instructions, and ignored `trusted_keys/`.
- Commands executed and test results: Focused API/provision tests: 12 passed. `scripts/check.ps1`: CHECK OK; 92 passed, 1 network test skipped; leak and language checks passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: The API reports malformed packets as HTTP JSON responses with status COMPROMISED and the exact reason `Malformed packet`; anti-replay state is in memory and resets on server restart. Event scenario labels are explicitly treated as assumed metadata.
- Remaining work / exact stopping point: Reread this entry, rerun `scripts/check.ps1` after the log update, then stage, commit, and push the P9 changes.
## [2026-10-27 23:06] Step P9 follow-up: Verify API and receiver
- Status: COMPLETED
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Re-ran the complete verification after the P9 log update.
  - All 93 tests passed, including the network-marked test; leak and language checks passed.
  - The only warning was an upstream Pydantic deprecation notice.
- Commands executed and test results: `scripts/check.ps1` - CHECK OK; 93 passed; leak check passed; language check passed.
- Decisions and assumptions: Network availability differed between the two full runs; the final verification completed the previously skipped network test.
- Remaining work / exact stopping point: Reread this entry, confirm the staged file list contains no prohibited data or keys, then commit and push on `main`.
## [2026-10-27 23:19] Step P10: Prepare Streamlit Community Cloud deployment
- Status: DONE
- Files created or modified: app.py, dashboard_pages/page_06_zone_scan.py, dashboard_pages/page_07_level_3_archive.py, dashboard_pages/page_12_kali_receiver.py, scripts/DEPLOY.md, scripts/build_deploy.py, space_static/index.html, tests/test_app_smoke.py, tests/test_build_deploy.py, tests/test_model_fetch.py, tp/model_fetch.py, DEVELOPMENT_LOGS.md; removed five surplus clean sample chip and metadata pairs from samples/.
- Summary of work completed (3-8 lines):
  - Added public Hugging Face model resolution and download for missing or empty artifacts, calibration validation, and a clear offline failure when no complete local model is available.
  - Added cached startup preparation, model source and SHA-256 display, online deployment banner, and 10-minute caches for live acquisition, zone grids, and archive checks.
  - Added deployment preflight reporting, standalone showcase HTML, deployment instructions, and reduced samples/ to 20 chips while retaining cloudy and regional examples.
  - Verified that the original model/ was restored after a cold download and ONNX self-test.
- Commands executed and test results: Focused P10 tests: 14 passed. Cold download from the public repository succeeded; self-test: ok=true, n=12, max_abs_diff=7.059574127055157e-06, max_prob_diff=1.633167266845703e-05. Deployment preflight: OK, 20 chips, 10.81 MB. `scripts/check.ps1`: CHECK OK; 103 passed; leak and language checks passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: The existing local model is ignored by Git and was restored intact after the cold-start simulation. No Hugging Face secret is needed for the public model. Five surplus clean samples were removed to meet the explicit 20-chip deployment cap.
- Remaining work / exact stopping point: Reread this entry, rerun `scripts/check.ps1` with the final log and deployment preflight, then stage, commit, and push P10 on `main`.

## [2026-10-27 23:30] Step P11: Finalize phase one
- Status: PARTIAL
- Files created or modified: README.md, scripts/measure.py, scripts/eval_samples.py, tests/test_e2e.py, reports/measurements.json, reports/eval_samples.csv, data_preparation.ipynb, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added an offline end-to-end test for all eight packet scenarios, report generation, all 17 forgery families, and retained the P1 legacy AST equivalence test.
  - Recorded real measurements for 50 ONNX runs, 50 verifier checks, 50 full pipeline runs, peak resident memory, and model size. Only 20 distinct sample chips were available, so inference inputs cycled through them; model download duration is not measured.
  - Evaluated 20 authentic samples and 20 fixed-seed strong forgeries per family; every CSV row carries the small sample, indicative only note.
  - Added the anonymous English README with measured values, attack expectations, deployment guidance, and the requested limitations and inherited-message note.
  - Anonymized detected account-name references in the ignored data-preparation notebook; the README, training notebook, and reports had no matching reference after the edit.
- Commands executed and test results: Measurement run completed: ONNX mean 79.76 ms / p95 95.06 ms; verifier mean 0.73 ms / p95 0.97 ms; full pipeline mean 204.71 ms / p95 222.04 ms; peak resident memory 260,329,472 bytes; model size 57.38 MB; download duration not measured. Sample evaluation completed for 20 authentic chips and 340 forged chips. Focused end-to-end and AST tests: 19 passed. Language check passed. Full project check and leak audit are pending.
- Decisions and assumptions: Since the sample directory contains 20 chips rather than 50, latency statistics represent 50 runs over those 20 unique chips with cycling explicitly reported. Cloudy classification uses the sample metadata hard flag. Forgery evaluation uses strong severity and deterministic per-family/per-chip seeds; all rates are indicative, not generalization estimates.
- Remaining work / exact stopping point: Run the complete project check, staged leak scan, and anonymity audit; then append final verification and the phase completion table, rerun checks, and perform the mandatory Git commit and push.

## [2026-10-27 23:33] Step P11 follow-up: Verify phase one and record final status
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The full project check passed with 121 tests; the only output warning was an upstream Pydantic deprecation notice.
  - Leak and language checks passed, including the staged-file scan after staging.
  - The anonymity audit found and anonymized account-name references in the ignored data-preparation notebook; no matching name, personal path, or email was found in the README, training notebook, or reports afterward.
  - The unique Git author audit returned one project-team author using the account's noreply address.
  - Deployment preflight passed with 20 sample chips and an 10.83 MB repository footprint.
- Commands executed and test results: `scripts/check.ps1` — CHECK OK; 121 passed; leak and language checks passed. `scripts.build_deploy` — all checks passed. Focused P11 tests — 19 passed. Decision equivalence remains covered by `tests/test_split.py`.
- Decisions and assumptions: Sample evaluation is fixed-seed and indicative only. The online model download duration was not measured. The repository author was not copied into this log.
- Remaining work / exact stopping point: Complete the Git commit and push; the manual deliverables below remain outside this repository task.

## Phase 1 completion table

| Step | Status | Main files | Tests passed |
| --- | --- | --- | --- |
| P-1.0 | DONE | `scripts/make_samples.py`, `samples/` | 25 sample pairs verified |
| P-1 | DONE | `.gitignore`, `scripts/check_leaks.py`, `scripts/check_language.py` | 14 |
| P0 | DONE | `requirements.txt`, `pytest.ini`, `.streamlit/config.toml` | 16 |
| P1 | DONE | `tp/attacks.py`, `tp/provenance.py`, `tp/data_io.py` | 31 |
| P2 | DONE | `tp/onnx_analyzer.py`, `tp/selftest.py` | 37 |
| P3 | DONE | `tp/contract.py`, `tp/sentinel_live.py` | 49 |
| P4 | DONE | `tp/engine.py`, `tests/test_engine.py` | 61 |
| P5 | DONE | `app.py`, `assets/`, `dashboard_pages/` | 63 |
| P6 | DONE | `dashboard_pages/page_01_mission_control.py`, `page_02_copernicus_acquisition.py`, `page_03_map.py` | 64 |
| P7 | DONE | `dashboard_pages/page_04_attack_lab.py`, `page_05_forensics.py` | 73 |
| P8 | DONE | `dashboard_pages/page_06_zone_scan.py` through `page_11_custom_upload.py` | 80 passed, 1 skipped |
| P9 | DONE | `api.py`, `attacker/`, `scripts/provision.py` | 93 |
| P10 | DONE | `tp/model_fetch.py`, `scripts/build_deploy.py`, `scripts/DEPLOY.md` | 103 |
| P11 | DONE | `README.md`, `scripts/measure.py`, `scripts/eval_samples.py`, `tests/test_e2e.py`, `reports/` | 121 |

### To do manually

- Capture final dashboard screenshots.
- Record the backup video.
- Deploy the dashboard and run the online checks.
- Publish the Hugging Face model card.
- Evaluate official challenge datasets separately.

## [2026-10-28 09:20] Step P11 follow-up: Record release checkpoint completion
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Recorded that the P11 implementation commit was already pushed successfully to `origin/main`.
  - Confirmed the prior stopping point about committing and pushing is complete.
- Commands executed and test results: `git push` succeeded for the P11 commit; the working tree was clean before creating the v2 checkpoint.
- Decisions and assumptions: No P11 source files changed in this follow-up.
- Remaining work / exact stopping point: Prepare the v2 baseline as requested before beginning dashboard changes.

## [2026-10-28 09:20] Step P12: Prepare dashboard v2 baseline
- Status: PARTIAL
- Files created or modified: AGENTS.md, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Confirmed a clean working tree on `main` and a green pre-change baseline: 121 tests passed, leak and language checks passed, `CHECK OK`.
  - Created and pushed the `v1-multipage` tag to preserve the current dashboard version.
  - Appended the single-page map dashboard v2 rules to `AGENTS.md` without changing the existing rules.
  - GitHub currently reports the repository visibility as PUBLIC; visibility was left unchanged.
- Commands executed and test results: `scripts/check.ps1` — CHECK OK, 121 passed. `git push origin v1-multipage` succeeded. `gh repo view` returned visibility PUBLIC. A post-edit check remains pending.
- Decisions and assumptions: The task is limited to preparing the baseline; no dashboard implementation has started. The earlier private-visibility note was stale, so the currently reported PUBLIC state is recorded without changing it.
- Remaining work / exact stopping point: Run `scripts/check.ps1` after the AGENTS/log updates, record the actual result, then commit and push the preparation change.

## [2026-10-28 09:20] Step P12 follow-up: Verify prepared dashboard v2 baseline
- Status: DONE
- Files created or modified: AGENTS.md, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The requested v2 single-page dashboard rules are appended at the end of `AGENTS.md`.
  - The `v1-multipage` tag points to the clean pre-change `main` commit and was pushed to `origin`.
  - The repository visibility was checked and remains PUBLIC, unchanged.
  - The post-edit project check passed with 121 tests; leak and language checks passed.
- Commands executed and test results: `scripts/check.ps1` — CHECK OK; 121 passed; leak check passed; language check passed. One upstream Pydantic deprecation warning was reported.
- Decisions and assumptions: This completes the requested preflight and instruction update only; no dashboard implementation files were changed.
- Remaining work / exact stopping point: Await the dashboard v2 implementation prompt, beginning with P12 work against this recorded baseline.

## [2026-10-28 09:33] Step P12b: Single-page dashboard skeleton
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Audited the legacy dashboard before removal. `app.py` contains the shared runtime, 13-page navigation, global banners, and selected-page dispatch; this entire shell will be replaced by the single-page entry point.
  - Old page files identified: `dashboard_pages/_qgis.py`, `dashboard_pages/_shared.py`, `dashboard_pages/copernicus_acquisition.py`, `dashboard_pages/model_card.py`, and `dashboard_pages/page_01_mission_control.py` through `dashboard_pages/page_12_kali_receiver.py`.
  - `assets/style.css` is old dashboard styling and will be replaced by `ui/theme.py`; `assets/logo.svg` is retained for the shared product identity.
  - Old UI-only tests identified: `tests/test_app_smoke.py` multipage cases, all of `tests/test_offline_pages.py`, and all of `tests/test_attack_forensics.py`. In `tests/test_pages_p8.py`, archive comparison and GeoTIFF export tests will move beside `tp.sentinel_live` and `tp.data_io`; audit simulation and custom-upload tests exercise deleted UI features. Report JSON/hash remains covered by `tests/test_engine.py`.
  - Runtime/API/security coverage retained: `tests/test_engine.py`, `test_api.py`, `test_split.py`, `test_provenance.py`, `test_attacks.py`, `test_onnx.py`, `test_contract.py`, `test_model_fetch.py`, `test_leaks.py`, `test_language.py`, and `test_e2e.py`; `test_provision.py`, `test_build_deploy.py`, and `test_assets.py` are also independent of old page navigation.
- Commands executed and test results: Read `AGENTS.md`, `DEVELOPMENT_LOGS.md`, and `README.md`; inventoried the UI/test files and package imports. Verified the EOX Tunisia tile URL for layer `s2cloudless-2023_3857` with a 3-second request; HTTP 200. Basemap attribution is taken from the current EOxCloudless license summary.
- Decisions and assumptions: Preserve pure archive and GeoTIFF helper tests by moving them to tests for retained `tp/` code. Remove tests only for deleted dashboard-only behaviors. The prior preparation remains Step P12; this implementation is logged as P12b, and subsequent work uses P13-P18.
- Remaining work / exact stopping point: Implement the new `ui/` package and one-page app, remove old pages and UI-only tests, update dependencies/README, add AppTest and basemap fallback tests, then run `pip check` and the full mandatory check.

## [2026-10-28 09:50] Step P12b follow-up: Implement and verify the single-page dashboard
- Status: DONE
- Files created or modified: app.py, ui/, assets/style.css (deleted), dashboard_pages/ (deleted), requirements.txt, README.md, tests/test_app_smoke.py, tests/test_map_view.py, tests/test_data_io.py, tests/test_sentinel_live.py, tests/test_attack_forensics.py (deleted), tests/test_offline_pages.py (deleted), tests/test_pages_p8.py (deleted), DEVELOPMENT_LOGS.md, scripts/check_language.py.
- Summary of work completed (3-8 lines):
  - Replaced the multipage entry point with one map and a sidebar mode switch. The exact removed UI files were `dashboard_pages/.gitkeep`, `_qgis.py`, `_shared.py`, `copernicus_acquisition.py`, `model_card.py`, `page_01_mission_control.py`, `page_02_copernicus_acquisition.py`, `page_03_map.py`, `page_04_attack_lab.py`, `page_05_forensics.py`, `page_06_zone_scan.py`, `page_07_level_3_archive.py`, `page_08_audit_log.py`, `page_09_report.py`, `page_10_batch.py`, `page_11_custom_upload.py`, and `page_12_kali_receiver.py`; `assets/style.css` was also removed and its theme moved to `ui/theme.py`.
  - Added `ui/__init__.py`, `theme.py`, `state.py`, `map_view.py`, `panel_analyze.py`, `panel_monitor.py`, and `status.py`; startup now caches model preparation, pipeline creation and self-test results, and the map remains available if model startup fails.
  - Added ordered basemap checks (EOX, Esri, OpenStreetMap, then dark no-tile fallback), manual selection, saved map view, map controls, inline legend and title, and a DivIcon marker. The EOX Tunisia probe returned HTTP 200; attribution follows the provider license.
  - Removed unused pinned requirements `matplotlib`, `plotly`, `pydeck`, and `reportlab`; `pip check` reported no broken requirements. Updated README structure and expanded authored-file language scanning to include `ui/*.py`.
  - Audited removed UI tests: `test_app_smoke.py` multipage assertions were replaced with the single-page smoke test; `test_offline_pages.py` and `test_attack_forensics.py` tested removed UI flows; `test_pages_p8.py` archive and GeoTIFF pure-logic tests were moved to `test_sentinel_live.py` and `test_data_io.py`; its UI audit/custom-upload cases were removed, while report JSON/hash remains covered by `test_engine.py`.
  - Kept the requested runtime/security suite: `test_engine.py`, `test_api.py`, `test_split.py`, `test_provenance.py`, `test_attacks.py`, `test_onnx.py`, `test_contract.py`, `test_model_fetch.py`, `test_leaks.py`, `test_language.py`, and `test_e2e.py`; `test_e2e.py` required no UI import changes. Also retained `test_provision.py`, `test_build_deploy.py`, and `test_assets.py`.
- Commands executed and test results: Focused UI/helper tests passed (8 passed). `pip check` reported `No broken requirements found`. `scripts/check.ps1` passed (107 tests, leak check and language check passed; `CHECK OK`); one upstream Pydantic deprecation warning was emitted. `git diff --check` passed. EOX tile probe returned HTTP 200.
- Decisions and assumptions: The dashboard v2 code was created without changing `tp/`, `api.py`, `attacker/`, or their retained tests. `st_folium` is a custom component not exposed in AppTest's element tree, so the smoke test asserts one actual `st_folium` render call. Folium includes its bundled stylesheet references, but the marker implementation uses `DivIcon` and does not instantiate a Bootstrap or Font Awesome marker icon.
- Remaining work / exact stopping point: Stage, review the staged file set and protected-path exclusions, commit as `P12b: Single-page dashboard skeleton`, and push the commit to `origin/main`.

## [2026-10-28 09:52] Step P12b follow-up: Record commit and push
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Committed the reviewed single-page dashboard implementation as `3f71409` with the requested P12b commit title.
  - Pushed the commit successfully to `origin/main`.
  - The pre-commit leak guard passed; the staged file review and final whitespace check passed.
- Commands executed and test results: `git commit -m "P12b: Single-page dashboard skeleton"` succeeded; `git push` updated `origin/main` from `cdf169f` to `3f71409`. The final pre-commit `scripts/check.ps1` run passed 107 tests, leak and language checks (`CHECK OK`); `pip check` reported no broken requirements.
- Decisions and assumptions: No push authentication changes or credential operations were needed.
- Remaining work / exact stopping point: No remaining P12b implementation work. Continue with P13 when requested.

## [2026-10-28 10:08] Step P13: Live Copernicus area analysis
- Status: PARTIAL
- Files created or modified: tp/sentinel_live.py, tp/geo.py, tp/engine.py, ui/panel_analyze.py, ui/map_view.py, ui/state.py, app.py, tests/test_geo.py, tests/test_sentinel_live.py, tests/test_panel_analyze.py, tests/test_map_view.py, tests/test_engine.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added point-based Sentinel-2 acquisition search, item retrieval, UTM-centered chip reads with even and clamped windows, SCL resampling, swath rejection, and exact source metadata fields. The copied legacy functions in `tp/sentinel_live.py` were not changed.
  - Added four-corner chip and preview footprints, EPSG:4326 raster reprojection with geographic bounds/fallback, and PNG data URI helpers for true colour, NDVI, and inferno probability overlays.
  - Implemented map-click area selection, the fixed-size preview, training-domain warning, cached acquisition date list, source-signing and single pipeline processing, cloud context, result/report card, map overlays, layer controls, and status-colored footprint.
  - Added a pipeline progress callback so the UI can show the verification and inference stages without invoking `process` more than once. Offline unseen-data mode remains disabled for P14.
  - Added unit, mocked-raster/STAC, panel AppTest, and network-marked real Tunis-point analysis coverage.
- Commands executed and test results: Focused P13 suite passed 29 tests. The full `scripts/check.ps1` passed 117 tests plus leak and language checks (`CHECK OK`); no tests were skipped, including the live Tunis-point test. `pip check` reported no broken requirements. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: Acquisition search is cached in the panel for 600 seconds. The exact chip footprint is computed from the source 10 m UTM grid; the click preview is the specified local geographic approximation. When a selected scene has an unusable swath window, the panel tries the remaining returned acquisitions in newest-first order.
- Remaining work / exact stopping point: Rerun the project check after this log update, review and stage the changes, then commit and push P13 to `origin/main`.

## [2026-10-28 10:10] Step P13 follow-up: Record verification and publication
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Rechecked the final logged P13 tree: 117 tests passed, and the leak and language checks passed (`CHECK OK`).
  - Confirmed dependency consistency with `pip check`; no broken requirements were found.
  - Committed the implementation as `b7da436` and pushed it successfully to `origin/main`.
- Commands executed and test results: `scripts/check.ps1` passed 117 tests with no skips; the network-marked Tunis point acquisition and analysis succeeded. `git commit -m "P13: Live Copernicus area analysis"` and `git push` succeeded. The commit pre-hook leak scan passed.
- Decisions and assumptions: No copied legacy algorithm was changed; new point-based functions were added alongside the existing implementations.
- Remaining work / exact stopping point: No remaining P13 work. Continue with P14 when requested.

## [2026-10-28 10:36] Step P14: Prepared unseen data and local tampering simulation
- Status: PARTIAL
- Files created or modified: app.py, scripts/build_deploy.py, scripts/build_unseen_pack.py, tests/test_build_unseen_pack.py, tests/test_map_view.py, tests/test_pack.py, tests/test_panel_analyze.py, tp/geo.py, tp/pack.py, ui/map_view.py, ui/panel_analyze.py, ui/state.py, unseen_pack/index.json, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added offline pack loading, place summaries, nearest-chip lookup, a resumable Planetary Computer pack builder, and held-out sample references without copying sample data.
  - Enabled prepared-source selection, preset place markers, snapped place selection, source-aware date labels, offline analysis, local source/transit tampering, ground-truth contours, and IoU/Dice reporting.
  - Extended deployment preflight to check the unseen pack chip count and 15 MiB limit; the current repository preflight reports 10.85 MB total and unseen_pack at 0.01 MB.
  - The checked-in unseen_pack/index.json contains relative references to existing held-out samples; it contains zero post-training scene chips because the live STAC request did not return during the retry window.
- Commands executed and test results: Focused P14 tests: 13 passed. `scripts/check.ps1`: 123 passed; leak scan passed; language scan passed; `CHECK OK`. `scripts/build_deploy.py`: all checks passed. `scripts/build_unseen_pack.py --max-total-mb 15` was attempted twice and stopped after the Planetary Computer request remained unresponsive for about one minute; no scene-download result is claimed.
- Decisions and assumptions: Preserve the requested post-training cutoff of 2026-10-01 and do not substitute held-out chips for unseen live acquisitions. Existing sample files remain untouched and are referenced from the pack index. Offline UI tests use a local Tunis held-out chip when post-training data is unavailable.
- Remaining work / exact stopping point: Network acquisition remains unverified and the post-training portion of unseen_pack is empty. Run ` .\\.venv\\Scripts\\python.exe -u -m scripts.build_unseen_pack --max-total-mb 15 ` from the repository root when Planetary Computer access is available; then verify post-training dates, cloudy/clean counts, and total size before updating this entry.

## [2026-10-28 10:39] Step P14 follow-up: Record post-stage verification and retry command
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Re-ran the mandatory project check after staging so leak scanning covered the staged files; all 123 tests passed, leak and language scans passed, and the script printed `CHECK OK`.
  - Confirmed deployment preflight passes with 20 sample chips, zero downloaded unseen chips, a 0.01 MB unseen_pack, and 10.85 MB total repository size.
  - Clarified the exact retry command here without rewriting the earlier P14 entry.
- Commands executed and test results: Post-stage `scripts/check.ps1` — 123 passed, leak check passed, language check passed, `CHECK OK`.
- Decisions and assumptions: The lack of a Planetary Computer response is recorded as an unresolved external network limitation; no scene data or fetch success is claimed.
- Remaining work / exact stopping point: When network access is available, run `.venv/Scripts/python.exe -u -m scripts.build_unseen_pack --max-total-mb 15` from the repository root and validate the downloaded post-training rows before marking P14 DONE.

## [2026-10-28 11:04] Step P15: Live monitor backend
- Status: PARTIAL
- Files created or modified: api.py, .gitignore, attacker/feed.py, attacker/scenarios.py, attacker/mitm_addon.py, attacker/attack_menu.py, attacker/places.json, attacker/README.md, scripts/export_places.py, scripts/record_session.py, tests/test_api.py, tests/test_live_monitor_tools.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Added enriched event records with monotonically increasing event IDs, preserved sequence cursors, nearest preset places, signed-manifest metadata, and RGB/probability PNG previews; malformed packets are logged without images.
  - Added localhost-only event archival that leaves the in-memory replay verifier intact, plus a bounded event query that handles a missing event file.
  - Added the prepared-chip feed, targeted attack controls and menu, generated Kali place centers, recording exporter, demo order documentation, and focused regression tests.
  - The prepared pack currently has chips only for Tunis and Beja; the feed can only rotate among places with actual prepared chips. No live event stream exists yet to export a populated demo_session artifact.
- Commands executed and test results: Focused P15 tests: 20 passed. scripts/check.ps1: 133 passed, leak check passed, language check passed, CHECK OK; one upstream Pydantic deprecation warning. git diff --check passed.
- Decisions and assumptions: The assumed_mode field is an untrusted test-client label and is documented as non-cryptographic. No event records or images were fabricated to create a demo session. The existing P14 post-training data limitation remains unresolved.
- Remaining work / exact stopping point: Run the packet feed after keys are provisioned and data is available, then execute .venv/Scripts/python.exe -m scripts.record_session to create and review a populated, sub-3-MB demo_session/. Stage/review, rerun the mandatory check, commit, and push.
## [2026-10-28 11:11] Step P15 follow-up: Verify final implementation
- Status: PARTIAL
- Files created or modified: attacker/attack_menu.py, attacker/mitm_addon.py, tests/test_live_monitor_tools.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Corrected the attack menu severity values to match the supported attack contract and reject unsupported family/severity controls in the proxy.
  - Confirmed the feed cycles round-robin over available prepared places, the direct TestClient feed sends six packets, and event reset preserves replay detection.
  - Re-read the P15 record and confirmed its status, verification results, and remaining work reflect the current tree.
- Commands executed and test results: Focused API/tool tests: 20 passed. Final source check before this log addition: scripts/check.ps1 passed 133 tests, leak and language checks, and printed CHECK OK; one upstream Pydantic deprecation warning. git diff --check passed.
- Decisions and assumptions: The P15 check is repeated after this append before commit. P14 still has no downloaded post-training scenes, and there are no runtime events to export as a genuine populated demo_session.
- Remaining work / exact stopping point: Repeat scripts/check.ps1 after this entry, stage and review the complete change set, then commit and push the P15 partial implementation to main.
## [2026-10-28 11:14] Step P15 follow-up: Record publication
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Reviewed the staged file set and confirmed the staged leak scan and whitespace check passed.
  - Committed the P15 backend and the already staged P14 work as commit aaa1836 on main.
  - Pushed commit aaa1836 successfully to origin/main.
- Commands executed and test results: scripts/check.ps1 passed 133 tests, leak and language checks, and printed CHECK OK before publication. git commit -m "P15: Live monitor backend" and git push succeeded.
- Decisions and assumptions: The combined commit preserves the staged P14 work already present in the index. No credentials or authentication settings were changed.
- Remaining work / exact stopping point: P15 remains PARTIAL until a populated demo_session is recorded and the prepared pack has chips for the remaining preset places. Run scripts.build_unseen_pack when Planetary Computer access is available, run the live feed after key provisioning, export the last 40 events, verify the demo_session is below 3 MB, then commit and push those data artifacts.
## [2026-10-28 11:52] Step P16: Live monitor dashboard
- Status: DONE
- Files created or modified: api.py, app.py, ui/map_view.py, ui/panel_monitor.py, ui/state.py, tests/test_panel_monitor.py, demo_session/events.json, demo_session/*_rgb.png, demo_session/*_heat.png, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Implemented the live monitor panel with one-second health checks, event polling, status counters, newest-first alerts, event details, JSON download, clear/cutoff behavior, and a three-second Streamlit fragment.
  - Added monitor-only map state and status-colored square footprints, place labels and markers, static/pulsing warning icons, selected-event RGB/heat overlays, and a recorded-session legend badge.
  - Added recorded-session fallback replay in source order, one event every three seconds, plus the required offline banner and API startup hint. The fallback data is six locally processed signed sample packets exported with their PNGs.
  - Extended API event rows with score thresholds and plausibility for the detail card; recorded-session export is 831,237 bytes, below the 3 MB limit.
  - Added AppTest coverage for all three counters, the single compromised pulse, alert clearing, offline fallback, latest-event reduction, and recorded PNG overlays.
- Commands executed and test results: Focused monitor/map tests passed (10 passed); full `scripts/check.ps1` passed 135 tests, 1 skipped, leak and language checks, and printed `CHECK OK`; the monitor tests passed again after the final app-state change (4 passed); `git diff --check` passed. One upstream Pydantic deprecation warning was emitted.
- Decisions and assumptions: st_folium remounts its iframe on a full app rerun, so the event panel polls every three seconds without remounting the map. The `Auto refresh` toggle and `Refresh now` button provide stable panel updates and an explicit map redraw while preserving its stored center and zoom. The packet’s signed geographic center is available, but the API event does not contain the projection origin and CRS required by `chip_footprint_4326`; event overlays therefore use its documented 2.56 km preview footprint fallback.
- Remaining work / exact stopping point: Rerun `scripts/check.ps1` after this log entry, review the final status and staged file list, then commit and push P16. P14 and P15 remain PARTIAL for their separately documented post-training pack coverage and live feed/demo history gaps.
## [2026-10-28 11:53] Step P16 checkpoint: End-of-step procedure pending
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Corrected the P16 status checkpoint: implementation and test work are complete, but the mandatory post-log check and Git publication have not yet completed.
  - The prior P16 entry's completion status is superseded by this checkpoint until the end-of-step procedure is verified.
- Commands executed and test results: The pre-log `scripts/check.ps1` run passed 135 tests, 1 skipped, leak and language checks, and printed `CHECK OK`.
- Decisions and assumptions: Keep P16 partial until the post-log check, commit, and push have actually completed.
- Remaining work / exact stopping point: Rerun `scripts/check.ps1`, stage and review only intended files, commit P16, and push to `origin/main`.
## [2026-10-28 11:56] Step P16 follow-up: Record final verification and publication
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Reran the mandatory project check after the P16 checkpoint log entry: 137 tests passed, the leak and language checks passed, and the script printed `CHECK OK`.
  - Reviewed the staged file set and confirmed no prohibited paths or key material were tracked.
  - Committed P16 as `74ea753` (`P16: Live monitor dashboard`) and pushed it successfully to `origin/main`.
- Commands executed and test results: `scripts/check.ps1` passed 137 tests with one upstream Pydantic deprecation warning; `git diff --cached --check` passed; commit leak scan passed; `git push` succeeded.
- Decisions and assumptions: The recorded session consists of six real local API processing results from signed prepared sample packets. The newly provisioned source key remains ignored and untracked.
- Remaining work / exact stopping point: No remaining P16 work. P14 and P15 retain their separately documented PARTIAL status and remaining acquisition/feed work.
## [2026-10-28 12:25] Step P17: Dashboard polish and robustness
- Status: PARTIAL
- Files created or modified: README.md, DEVELOPMENT_LOGS.md, api.py, app.py, scripts/DEPLOY.md, tests/test_api.py, tests/test_app_smoke.py, tests/test_language.py, tests/test_model_fetch.py, tests/test_panel_analyze.py, tests/test_panel_monitor.py, tests/test_theme_accessibility.py, tp/model_fetch.py, ui/language.py, ui/map_view.py, ui/panel_analyze.py, ui/panel_monitor.py, ui/theme.py.
- Summary of work completed (3-8 lines):
  - Improved contrast, responsive spacing, keyboard focus visibility, empty states, loading feedback, technical help text, and missing-source explanations; removed duplicated inline styling.
  - Cached analysis overlays and monitor PNG data URIs, retained the 10-minute acquisition cache, added an observation-ID processing guard, and instrumented click-to-result time.
  - Hardened event image path containment and ID validation; API polling now ignores malformed or partial JSONL rows and safely handles a missing stream file.
  - Updated README and deployment test instructions; added AppTest, API partial-line, path-safety, language, and WCAG contrast coverage.
  - Measured 280.8 ms for a prepared chip and 24,966.6 ms for a live chip from click to result in this environment.
- Commands executed and test results: Focused dashboard/API tests passed (31 passed); the real Copernicus timing test passed. `pip check` reported no broken requirements. An initial full-suite run found a stale mocked Hugging Face function signature after the timeout addition; the test double was updated. The mandatory post-log `scripts/check.ps1` run is pending.
- Decisions and assumptions: Hugging Face Hub's built-in metadata and download timeouts are 10 seconds; `etag_timeout=10` makes metadata access explicit. Timing results describe one prepared and one live run and are not performance guarantees. Live monitor map iframe updates remain manual because `st_folium` remounts on full reruns.
- Remaining work / exact stopping point: Run the mandatory `scripts/check.ps1`, repeat `pip check`, review tracked paths and language, correct any failures, update this entry with final results, then commit and push P17.

## [2026-10-28 12:28] Step P17 checkpoint: Verification complete, publication pending
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Reran the mandatory project check after the P17 implementation log entry: 140 tests passed, 3 skipped, leak and language checks passed, and the script printed CHECK OK.
  - `pip check` reported no broken requirements; `git diff --check` passed.
  - Confirmed no prohibited model, docs, legacy, raw data, key, PEM, environment, or leak-word paths are tracked.
- Commands executed and test results: `scripts/check.ps1`: 140 passed, 3 skipped, one upstream Pydantic deprecation warning, leak check passed, language check passed, CHECK OK. `python -m pip check`: no broken requirements found.
- Decisions and assumptions: The prepared and live click-to-result measurements remain 280.8 ms and 24,966.6 ms for the observed runs.
- Remaining work / exact stopping point: Repeat `scripts/check.ps1` after this checkpoint, then stage, review, commit, and push the P17 implementation.

## [2026-10-28 12:32] Step P17 follow-up: Final verification and publication
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Repeated the mandatory check after the publication checkpoint: 143 tests passed, leak and language checks passed, and the script printed CHECK OK.
  - Confirmed pip check found no broken requirements and the staged whitespace/security review passed.
  - Committed P17 as 1f700af (P17: Dashboard polish and robustness) and pushed it to origin/main.
- Commands executed and test results: `scripts/check.ps1`: 143 passed, one upstream Pydantic deprecation warning, leak check passed, language check passed, CHECK OK. `python -m pip check`: no broken requirements found. `git diff --cached --check` passed; commit leak check passed; `git push` succeeded.
- Decisions and assumptions: The measured click-to-result observations were 280.8 ms for a prepared chip and 24,966.6 ms for a live chip; these are single-run observations, not guarantees.
- Remaining work / exact stopping point: No remaining P17 work. P14 and P15 retain their separately documented partial pack and feed coverage gaps.

## [2026-10-28 12:34] Step P17 cleanup: Remove unused cached layer builder
- Status: PARTIAL
- Files created or modified: ui/map_view.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Removed an unused prepared-place layer builder discovered during final review; the active monitor footprint cache remains in use.
  - Ran the focused map tests: 7 passed.
- Commands executed and test results: `python -m pytest tests/test_map_view.py -q`: 7 passed, one upstream Pydantic deprecation warning. Full post-cleanup check is pending.
- Decisions and assumptions: No rendered map behavior changed because the removed function had no callers.
- Remaining work / exact stopping point: Rerun the mandatory project check, then record the verified cleanup and publish it.

## [2026-10-28 12:36] Step P17 cleanup follow-up: Final check and publication
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Repeated the mandatory project check after cleanup: 143 tests passed, leak and language checks passed, and the script printed CHECK OK.
  - Confirmed the unused prepared-place layer builder is removed and the cached monitor footprint path still passes its map tests.
  - Committed the cleanup as 8b77fe6 and pushed it to origin/main.
- Commands executed and test results: Focused map tests passed (7 passed); `scripts/check.ps1` passed 143 tests with one upstream Pydantic deprecation warning, leak and language checks, and CHECK OK. `git diff --cached --check` and commit leak check passed; `git push` succeeded.
- Decisions and assumptions: The cleanup removed an unreferenced helper only; active map output did not change.
- Remaining work / exact stopping point: No remaining P17 work. P14 and P15 retain their separately documented partial pack and feed coverage gaps.

## [2026-10-28 13:02] Step P18: Final Dashboard v2 verification
- Status: PARTIAL
- Files created or modified: README.md, reports/measurements.json, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Ran the deployment preflight: all checks passed, including a tracked deployment payload size of 11.77 MB and no prohibited tracked paths.
  - Cold-started the dashboard with `model/` temporarily renamed; AppTest confirmed the public Hugging Face download and `Model OK` self-test result. Restored the original model directory and removed temporary test files.
  - Ran the offline prepared-chip AppTest through original analysis, strong inpaint_ns source tampering, and in-transit tampering; ran the mocked Live monitor red-alert AppTest.
  - Started the API locally, sent four packets with `attacker.feed --direct`, then sent pixels, replay, strip, and stolen_key scenarios using `attacker.scenarios`; verified nine events and 18 PNGs in isolated temporary storage.
  - Refreshed `reports/measurements.json` and synchronized the README measurements paragraph. Fresh measurements: ONNX mean 80.96 ms / p95 87.87 ms; verify mean 0.62 ms / p95 0.84 ms; pipeline mean 201.19 ms / p95 205.94 ms; peak memory 261,021,696 bytes; prepared click-to-result 335.9 ms.
- Commands executed and test results: `scripts.build_deploy` passed at 11.77 MB; cold-start AppTest passed; offline scenario AppTests passed (2); live API scenario passed (9 events, 18 PNGs; five TRUSTED and four COMPROMISED); restored-model self-test passed (`ok: true`); `scripts.measure` completed 50 runs in each benchmark group. Final `scripts.check.ps1` is pending after this entry.
- Decisions and assumptions: The cold-start test used the public repository `trustthepixel/trust-the-pixel-detector` without authentication and restored the original ignored model directory. All API events and generated PNGs used isolated scratch storage, which was removed after verification. Live dashboard click-to-result and model download duration are marked `not measured` in the report.
- Remaining work / exact stopping point: Run the mandatory final `scripts/check.ps1`, verify the final P18 log entry and staged protected-path/anonymity scans, commit and push the P18 verification record. Deployment, public release actions, screenshots/video, and official-dataset evaluation remain manual.

### Dashboard v2 final status table

| Step | Status | Main files | Tests and verification |
|---|---|---|---|
| P12 (including P12b) | DONE | `AGENTS.md`, `app.py`, `ui/`, `requirements.txt` | Baseline check: 121 passed; single-page implementation check: 107 passed; `pip check` passed. |
| P13 | DONE | `tp/sentinel_live.py`, `tp/geo.py`, `tp/engine.py`, `ui/panel_analyze.py` | 117 passed, including live Tunis acquisition; leak/language checks passed. |
| P14 | PARTIAL | `tp/pack.py`, `scripts/build_unseen_pack.py`, `ui/panel_analyze.py` | 123 passed; preflight passed. Post-training pack acquisition timed out, so prepared unseen-place coverage remains incomplete. |
| P15 | PARTIAL | `api.py`, `attacker/feed.py`, `attacker/scenarios.py`, `attacker/mitm_addon.py` | 133 passed; API, targeting, feed, and menu tests passed. Remaining pack/feed coverage is documented in earlier entries. |
| P16 | DONE | `ui/panel_monitor.py`, `ui/map_view.py`, `app.py`, `demo_session/` | 137 passed, 1 skipped; monitor counters, pulse, clear, and recorded fallback AppTests passed. |
| P17 | DONE | `ui/`, `api.py`, `app.py`, `README.md`, `scripts/DEPLOY.md` | Final check: 143 passed; leak/language checks and `pip check` passed. |
| P18 | PARTIAL | `README.md`, `reports/measurements.json`, `DEVELOPMENT_LOGS.md` | Preflight, cold start, offline AppTests, live API/feed scenarios, model self-test, and measurements passed; final full check pending. |

### To do manually

- Run the Kali VM proxy/feed/menu demonstration.
- Deploy and smoke-test on Streamlit Community Cloud.
- Confirm or perform the requested public repository release.
- Publish the Hugging Face model card.
- Add approved screenshots and record a backup video.
- Evaluate on official datasets.

## [2026-10-28 13:08] Step P18 checkpoint: Verification results complete
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The cold-start, prepared-chip and mocked monitor AppTests passed; the live API/feed scenario produced nine events and 18 PNG artifacts before temporary storage cleanup.
  - Restored-model self-test returned `ok: true`; the model backup, API process, and temporary test files are absent.
  - Repeated the final deployment preflight after report and README updates: all checks passed and tracked deployment content remains 11.77 MB.
  - Leak, language, protected-path, absolute-path, and commit-author audits passed; the audited author label is the team alias `tp-team`.
- Commands executed and test results: `scripts.build_deploy` passed; `scripts.check_leaks` and `scripts.check_language` passed; `scripts.check.ps1` passed 143 tests with one upstream Pydantic deprecation warning, leak/language checks, and CHECK OK. The final post-checkpoint check and publication are pending.
- Decisions and assumptions: P18 is PARTIAL because the user-specified deployment, public-release, screenshots/video, Kali demonstration, model-card, and official-dataset tasks are explicitly listed for manual completion.
- Remaining work / exact stopping point: Rerun `scripts/check.ps1` after this log checkpoint, then stage, review, commit, and push P18.

## [2026-10-28 13:14] Step P18 follow-up: Record final network-aware check
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The post-checkpoint full project check passed with 142 tests passed and one network test skipped; the leak and language checks passed and the script returned CHECK OK.
  - Identified the skip by running the network-marked tests with skip reasons: `tests/test_contract.py` could not read Planetary Computer after three attempts. The other two network-marked tests passed.
  - Repeated deployment preflight: all checks passed and deployment content was 11.77 MB. No prohibited paths are tracked.
  - The completed cold-start test used the public Hugging Face repository and passed; an initial temporary test-harness relative path was corrected before the successful run.
- Commands executed and test results: `scripts/check.ps1`: 142 passed, 1 skipped due Planetary Computer `RasterioIOError` after three attempts, one upstream Pydantic deprecation warning, leak/language checks passed, CHECK OK. `python -m pytest -m network -q -rs`: 2 passed, 1 skipped for the same Planetary Computer error. `scripts.build_deploy`: passed, 11.77 MB.
- Decisions and assumptions: The P18 row in the final status table above is superseded by this exact final count. The unavailable Planetary Computer network test is reported as skipped rather than treated as a successful live acquisition.
- Remaining work / exact stopping point: Rerun `scripts/check.ps1` after this update, then stage, commit, and push the P18 verification artifacts and log.

| Step | Status | Main files | Final tests and verification update |
|---|---|---|---|
| P18 | PARTIAL | `README.md`, `reports/measurements.json`, `DEVELOPMENT_LOGS.md` | 142 passed, 1 skipped (Planetary Computer network read failed after three attempts); preflight passed at 11.77 MB; cold start, offline AppTests, and local API scenarios passed. |

## [2026-10-28 13:20] Step P18 follow-up: Stabilize network timing test
- Status: PARTIAL
- Files created or modified: tests/test_panel_analyze.py, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - A full-check rerun failed because the network-dependent live timing test assumed Planetary Computer would return a usable chip; the panel correctly rendered an unavailable result instead.
  - Updated the test to skip only when the panel reports explicit acquisition or usable-swath unavailability, while retaining a failure for other cases that produce no measurement.
  - Reran the focused live timing test; it passed when the service returned a usable chip.
- Commands executed and test results: The failed full check reported 141 passed, 1 failed, and 1 skipped; the failure was `test_live_chip_click_to_result_timing` with no `area_last_source` after live acquisition errors. The corrected focused test passed (1 passed). Final full check is pending.
- Decisions and assumptions: A network-specific timing observation is optional for P18; the prepared-chip click-to-result measurement remains the reported UI timing.
- Remaining work / exact stopping point: Rerun `scripts/check.ps1`; record the actual outcome and skip reasons, then complete P18 publication.

## [2026-10-28 13:23] Step P18 follow-up: Final verified outcome
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - The corrected post-log full check passed: 143 tests passed, leak and language checks passed, and the script printed CHECK OK.
  - Deployment preflight passed after the P18 changes; deployment content measured 11.78 MB, below the 100 MB limit, with no prohibited tracked paths.
  - Cold start, restored-model self-test, offline/tampering AppTests, the mocked compromised alert, and the real local API/feed scenarios passed.
  - Anonymity checks found no personal names, email addresses, or absolute paths in the requested README, reports, recorded-session, and unseen-pack JSON content; Git commit authors are labeled `tp-team`.
- Commands executed and test results: `scripts.check.ps1`: 143 passed, one upstream Pydantic deprecation warning, leak/language checks passed, CHECK OK. `scripts.build_deploy`: passed at 11.78 MB. `scripts.check_leaks` and `scripts.check_language` passed. P18's prepared click measurement is 335.9 ms; live click and model download durations remain `not measured` in the report.
- Decisions and assumptions: The earlier P18 table update showing 142 passed and one skipped is superseded by this final successful check; the temporary network skip was not present in the final run.
- Remaining work / exact stopping point: Stage and review P18 changes, commit and push. Manual release/demo, screenshots/video, model-card, and official-dataset tasks remain listed below.

| Step | Status | Main files | Final tests and verification update |
|---|---|---|---|
| P18 | PARTIAL | `README.md`, `reports/measurements.json`, `DEVELOPMENT_LOGS.md` | Final `scripts/check.ps1`: 143 passed, no skipped tests; preflight passed at 11.78 MB; cold start, offline AppTests, and local API scenarios passed. |

To do manually: run the Kali VM demo; deploy on Streamlit Community Cloud; confirm/perform the public repository release; publish the Hugging Face model card; add screenshots; record a backup video; evaluate official datasets.

## [2026-10-28 13:27] Step P18 follow-up: Capture live click timing
- Status: PARTIAL
- Files created or modified: README.md, reports/measurements.json, DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Captured a successful live-chip AppTest click-to-result measurement: 7,478.4 ms including acquisition; the prepared-chip result remains 335.9 ms.
  - Updated the measurements report with both run timestamps and synchronized the README measurements paragraph.
  - The earlier P18 statement that live click time was not measured is superseded; model download duration remains `not measured`.
- Commands executed and test results: `python -m pytest tests/test_panel_analyze.py::test_live_chip_click_to_result_timing -q -s`: 1 passed, with one upstream Pydantic deprecation warning. The required full check after this report/log update is pending.
- Decisions and assumptions: Both click timings are one-run AppTest observations. The live value includes acquisition and is not directly comparable to prepared-chip processing time.
- Remaining work / exact stopping point: Run `scripts/check.ps1` and deployment preflight after this entry, then publish the P18 changes. P18 remains PARTIAL for the manual tasks listed above.

| Step | Status | Main files | Final tests and verification update |
|---|---|---|---|
| P18 | PARTIAL | `README.md`, `reports/measurements.json`, `DEVELOPMENT_LOGS.md`, `tests/test_panel_analyze.py` | 143 tests passed on the preceding full run; one live timing run measured 7,478.4 ms; model download time remains not measured; preflight passed at 11.78 MB. |

Audit scope note: `check_leaks` passed, and the explicit content search found no known local username, email, or absolute-path patterns in the requested content. This is a pattern-based audit, not a semantic scan for every possible personal name.

## [2026-10-28 13:31] Step P18 follow-up: Final required checks
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Reran the required full check after the current P18 log entry: all 143 tests passed, leak and language checks passed, and the script printed CHECK OK.
  - Reran deployment preflight: all checks passed; repository deployment content measured 11.78 MB, below the 100 MB limit.
  - Confirmed git ls-files reports no tracked files under model/, docs/, legacy/, data_raw/, keys/, events_data/, or events_archive/.
  - Git author audit shows the project alias tp-team; the requested content scan was pattern-based and reported no known username, email, or absolute-path matches.
- Commands executed and test results: scripts/check.ps1: 143 passed, 1 upstream Pydantic deprecation warning, leak/language checks passed, CHECK OK. scripts.build_deploy: passed at 11.78 MB. git diff --check: passed.
- Decisions and assumptions: P18 remains PARTIAL because deployment, public release, screenshots/video, Kali demonstration, model-card, and official-dataset work are manual follow-ups.
- Remaining work / exact stopping point: Stage/review, commit and push. Record actual publication result in a follow-up entry.
## [2026-10-28 13:35] Step P18 publication result
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Committed the verified P18 changes as 7b44401 (P18: Final Dashboard v2 verification).
  - Pushed the commit successfully to origin/main.
  - The mandatory full check immediately before publication passed: 143 tests, leak and language checks passed, CHECK OK.
- Commands executed and test results: git commit succeeded; git push succeeded and advanced main from 7369879 to 7b44401.
- Decisions and assumptions: P18 remains PARTIAL because the seven manual follow-ups in the To do manually list are outside this local verification step.
- Remaining work / exact stopping point: Verify this final log-only update, then commit and push it.
## [2026-10-28 17:00] Step P18 follow-up: Expand visitor setup guide
- Status: PARTIAL
- Files created or modified: README.md, attacker/README.md, DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Replaced the short local-run notes with a visitor-oriented Windows setup, local API and dashboard commands, and prepared-chip offline path.
  - Added end-to-end VirtualBox and Kali instructions, including downloads, import, host-only networking, optional NAT package installation, file copy, proxy environment setup, menu selection, feed launch, and cleanup.
  - Corrected the Kali proxy instructions to set PYTHONPATH so the add-on can import the copied tp package.
  - Removed the standalone Limitations section and kept factual scope, recorded-session, data provenance, and map attribution details in relevant sections.
- Commands executed and test results: README and attacker README content reviewed; `git diff --check` passed. Required `scripts/check.ps1` is pending.
- Decisions and assumptions: The guide retains clear statements that this is a controlled local simulation and that the source signature is not issued by Copernicus; these describe what the demo does and avoid presenting simulated evidence as operational satellite provenance.
- Remaining work / exact stopping point: Run `scripts/check.ps1`, review the final diff and tracked-file scope, then commit and push. P18 remains PARTIAL for its previously documented manual release and evaluation items.
## [2026-10-28 17:18] Step P18 follow-up: Visitor guide verification
- Status: PARTIAL
- Files created or modified: README.md, attacker/README.md, DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Updated the language-check failure by removing non-English localized UI strings from the visitor guide while keeping the VirtualBox instructions understandable in English.
  - Corrected the copyable Windows PowerShell commands in the attacker quick-start and retained the required Kali PYTHONPATH setup.
  - The required full check passed after the documentation corrections: all 143 tests passed, leak and language checks passed, and the script reported CHECK OK.
- Commands executed and test results: An initial full check caught French localized menu terms in README.md (142 passed, 1 failed); those terms were replaced with English descriptions. A subsequent `scripts/check.ps1` passed: 143 passed, one upstream Pydantic deprecation warning, leak check passed, language check passed, CHECK OK. `git diff --check` passed.
- Decisions and assumptions: This documentation follow-up remains part of P18; its overall status remains PARTIAL because the manual release, deployment, screenshots/video, Kali demonstration, model-card, and official-dataset tasks listed in the P18 table remain pending.
- Remaining work / exact stopping point: Reread this log entry after the required post-log check, review the documentation diff, then stage, commit, and push the changes. Record the actual publication result in a final log entry.
## [2026-10-28 17:25] Step P18 follow-up: Post-log check outcome
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Reran the mandatory full check after adding the visitor-guide verification entry.
  - All 142 tests passed; one network-dependent test was skipped by the suite.
  - Leak and language checks passed, and the script printed CHECK OK.
- Commands executed and test results: `scripts/check.ps1`: 142 passed, 1 skipped, one upstream Pydantic deprecation warning; leak check passed; language check passed; CHECK OK.
- Decisions and assumptions: The one skipped network test is reported as skipped; no live acquisition result is inferred from it.
- Remaining work / exact stopping point: Perform the final check, review and stage the three intended documentation/log files, then commit and push. Record publication outcome afterward.
## [2026-10-28 17:34] Step P18 visitor guide publication result
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Committed the expanded Windows and Kali visitor guide, corrected attacker quick-start, and verification log as 62ed63a (P18: Expand visitor setup guide).
  - Pushed the commit successfully to origin/main.
  - The mandatory full check after the preceding log update passed: 142 tests passed, 1 network-dependent test skipped, leak and language checks passed, CHECK OK.
- Commands executed and test results: git commit succeeded; git push succeeded and advanced main from 9a73a72 to 62ed63a. `scripts/check.ps1`: 142 passed, 1 skipped, one upstream Pydantic deprecation warning; CHECK OK.
- Decisions and assumptions: P18 remains PARTIAL for the previously recorded manual demonstration and release tasks.
- Remaining work / exact stopping point: Run the required check after this publication entry, then stage, commit, and push the final log update.
## [2026-10-28 17:42] Step P18 follow-up: Close visitor guide verification
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3-8 lines):
  - Completed the post-publication check that was pending in the previous entry: 143 tests passed, leak and language checks passed, and CHECK OK was reported.
  - Confirmed the visitor-guide commit 62ed63a and the accompanying log commit a1238a6 were both pushed to origin/main.
  - Confirmed the working tree is clean after publication.
- Commands executed and test results: `scripts/check.ps1`: 143 passed, one upstream Pydantic deprecation warning, leak check passed, language check passed, CHECK OK. `git status --short` returned no changes; `git push` succeeded for both commits.
- Decisions and assumptions: P18 remains PARTIAL because its separately listed manual release, deployment, screenshots/video, Kali demonstration, model-card, and official-dataset tasks remain open.
- Remaining work / exact stopping point: No further README work remains. The next P18 work is the previously listed manual demo and release follow-ups.

## [2026-11-01 00:00] Step P19: Integrate ZIP features and configurable service connections
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Began comparing the current implementation with `trustthesatellite-main.zip` and identified missing chain, device protocol, copy-move forensics, kernel exploration, and workspace modules.
  - Excluded the ZIP's GIS export code and static Next.js prototype as requested.
  - Confirmed the dashboard currently probes and polls a local-loopback API by default, while model files are fetched through `HF_MODEL_REPO` with a compiled fallback.
  - The requested remote backend endpoint has not been provided; service configuration will be made explicit and environment/Streamlit-secret driven.
- Commands executed and test results: Inspected current source, tests, and ZIP contents without extracting or modifying archive files. `.venv\Scripts\python.exe` is not present, so project tests are not currently runnable through the required environment.
- Decisions and assumptions: The one-page, two-mode dashboard constraint remains in force; ZIP-only capabilities will be integrated into the existing modes or backend where compatible. An explicit deployment URL cannot be invented.
- Remaining work / exact stopping point: Implement compatible missing modules and configurable model/backend connection behavior, add regression tests, run required checks if the project virtual environment can be made available, review the final entry, then commit and push if repository access permits.

## [2026-11-01 12:31] Step P19 follow-up: Backend routing and ZIP feature integration
- Status: PARTIAL
- Files created or modified: `.gitignore`, `.streamlit/secrets.example.toml`, `README.md`, `api.py`, `app.py`, `attacker/`, `scripts/DEPLOY.md`, `scripts/`, `tests/`, `tp/`, `ui/`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Added chained legacy packets, TPX2 device packets and attack scenarios, chain and copy-move evidence, optional kernel analysis, and a map workspace card from the reference archive. The static Next.js prototype was not copied; existing GIS code was left outside this change.
  - Added backend `/analyze` processing for signed dashboard packets, backend model acquisition from the configured Hugging Face repository, and live health/events polling through configured URLs.
  - Removed compiled backend/model repository defaults from active root runtime code. Runtime configuration uses environment variables or Streamlit secrets; backend analysis requires a source private key configured outside the repository and its public key trusted by the API.
  - Added API, configuration, model fetch, chain, TPX2, forensics, kernel, workspace, and remote panel tests.
- Commands executed and test results: `git diff --check` passed. `scripts/check.ps1` exited 1 before pytest because `.venv\Scripts\python.exe` is missing; pytest, leak, and language checks did not run. Active root Python runtime scan found no fixed API loopback/proxy URL or model repository fallback.
- Decisions and assumptions: The dashboard remains one page with the two existing modes. `TP_API_URL` is the API `/health` URL; backend analysis is used when it is configured and healthy, and local inference is used when it is unset. No deployment URL or private key was supplied, so those values remain deployment configuration.
- Remaining work / exact stopping point: Configure `HF_MODEL_REPO`, `TP_API_URL`, `TP_SOURCE_PRIVATE_KEY`, and the paired public key in the API runtime; provision the backend at a reachable HTTPS address; rerun `scripts/check.ps1` when the project virtual environment exists; then commit and push. The P19 step remains PARTIAL until those checks and publication complete.

Correction to the initial P19 entry: its placeholder time was `00:00`; the work began on 2026-11-01 during the local afternoon. Its feature note should be read as excluding the static Next.js prototype and not adding GIS export functionality.

## [2026-11-01 12:32] Step P19 follow-up: Local commit and remote push result
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Committed the P19 implementation as `d1027fb` (`P19: Integrate backend and ZIP features`).
  - Attempted `git push origin main`; the remote rejected it because `main` contains commits not present locally (non-fast-forward), not because of authentication.
  - Kept the local commit and did not force-push or alter credentials.
- Commands executed and test results: `git commit` succeeded. `git push origin main` was rejected with “fetch first”. The required check remains blocked by the missing `.venv\Scripts\python.exe`; `git diff --check` passed.
- Decisions and assumptions: Remote history must be synchronized before the P19 commit can be pushed. Do not overwrite remote work.
- Remaining work / exact stopping point: Safely synchronize `main` with `origin/main`, resolve any conflicts, rerun `scripts/check.ps1` with the project virtual environment, then push. The P19 work remains PARTIAL.

## [2026-11-01 12:33] Step P19 follow-up: Push requires manual GitHub authentication
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Recorded that a second `git push origin main` could not complete because Git could not open an interactive GitHub username prompt in this environment.
  - No credentials or authentication settings were changed.
  - Both P19 commits remain local; the earlier push also reported that `origin/main` has commits missing locally.
- Commands executed and test results: `git push origin main` failed with `fatal: could not read Username for 'https://github.com': No such device or address`; required checks remain unavailable because `.venv\Scripts\python.exe` is missing.
- Decisions and assumptions: Do not force-push or manipulate credentials. The user must authenticate and synchronize remote history manually before pushing.
- Remaining work / exact stopping point: Run `git pull --rebase origin main`, resolve any conflicts, then run `git push origin main` manually. Rerun `scripts/check.ps1` after restoring the project virtual environment. P19 remains PARTIAL.

## [2026-11-01 13:02] Step P20: Diagnose Hugging Face model download failures
- Status: PARTIAL
- Files created or modified: `tp/model_fetch.py`, `tests/test_model_fetch.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Started improving model fetch errors because the configured public repository lists all required artifacts and direct HEAD requests succeeded, while the Python downloader still reported only a generic failure.
  - Updated the downloader to identify the artifact and exception class without printing the exception message or potentially sensitive transfer URLs.
  - Updated the offline failure test to assert the more actionable, sanitized diagnostic.
- Commands executed and test results: Not run yet; next run `scripts/check.ps1` with the project virtual environment and execute the fetch command to confirm behavior.
- Decisions and assumptions: The repository is public, so Hugging Face login/upload commands are unnecessary. PowerShell cannot execute Python import statements directly; use the project Python executable with `-m`.
- Remaining work / exact stopping point: Run required checks, inspect actual downloader error from the user-facing command, reread this entry, then complete the required git workflow as permitted.

## [2026-11-01 13:08] Step P20 follow-up: Fix downloader and capture actual network result
- Status: PARTIAL
- Files created or modified: `tp/model_fetch.py`, `tests/test_model_fetch.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - The improved error identified a local `NameError`; added the missing `os` import used to atomically replace downloaded files.
  - The model fetch test module passes all 7 tests.
  - A real fetch attempt now reports a DNS resolution failure (`getaddrinfo failed`) for Hugging Face in this execution environment; the configured repository and file name were recognized.
- Commands executed and test results: `python -m pytest tests/test_model_fetch.py -q` passed (7 passed). `scripts/check.ps1` failed during pytest collection because duplicate test basenames exist in nested project copies, and its leak scan reports prohibited artifacts in those copies. `python -m tp.model_fetch` exited 1 after DNS retries; no successful download is claimed.
- Decisions and assumptions: User-side PowerShell HEAD requests previously returned HTTP 200, so DNS failure here may be specific to this runtime/network path. The sanitized downloader message intentionally avoids echoing exception text or transfer URLs.
- Remaining work / exact stopping point: User should rerun the fetch command after the local `NameError` fix in their PowerShell environment. Diagnose proxy/DNS routing only if the new error persists. Resolve nested checkout collisions separately; finish the P20 git workflow without staging the unrelated `kernel_figure.png`.

## [2026-11-01 13:10] Step P20 follow-up: Commit and push outcome
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Committed the P20 downloader diagnostic and test changes as `62f1d1f` (`P20: Diagnose Hugging Face model download`).
  - Attempted the required push; `origin/main` rejected it because the remote has commits not present locally.
  - Kept the commit and did not force-push or alter credentials.
- Commands executed and test results: `git add` and `git commit` succeeded. `git push origin main` failed with “fetch first”.
- Decisions and assumptions: Preserve remote history; synchronize before pushing.
- Remaining work / exact stopping point: Run `git pull --rebase origin main`, resolve conflicts if any, then push. User can now rerun `HF_MODEL_REPO='trustthepixel/trust-the-pixel-detector'; .\.venv\Scripts\python.exe -m tp.model_fetch` in the networked PowerShell session.

## [2026-11-01 13:20] Step P21: Use one configured backend for dashboard inference
- Status: PARTIAL
- Files created or modified: `app.py`, `tests/test_app_smoke.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Confirmed the root dashboard is a single page with Analyze area and Live monitor modes, with image overlays and forensic evidence in the analysis result.
  - Started removing duplicate frontend-side model initialization when `TP_API_URL` is configured, so the backend owns Hugging Face model loading and inference.
  - Kept local model inference for the no-backend development/offline path.
- Commands executed and test results: Not run yet; targeted dashboard checks and `scripts/check.ps1` remain to be run.
- Decisions and assumptions: Backend URL configuration is the explicit routing switch. When set, failed backend connectivity must remain visible and must not silently imply backend inference.
- Remaining work / exact stopping point: Implement and verify remote-first startup, reread this entry, then commit and attempt the required push without staging unrelated files.

## [2026-11-01 13:46] Step P21 resumed: Restore the requested Streamlit navigation design
- Status: PARTIAL
- Files created or modified: `app.py`, `pytest.ini`, `scripts/check_leaks.py`, `tests/test_app_smoke.py`, `tests/test_leaks.py`, `DEVELOPMENT_LOGS.md`; staged removals of nested duplicate projects, the static Next.js prototype, and protected model/training artifacts.
- Summary of work completed (3–8 lines):
  - The user clarified that the target is the branded full-function sidebar design with project details and map in the main workspace.
  - The backend-first model startup change is implemented and its focused test passed.
  - Began consolidating tracked duplicate app trees and removing the excluded static prototype and tracked model artifacts while preserving locally downloaded model files.
- Commands executed and test results: The focused backend-startup test passed. The leak-check unit tests passed (11 passed); the repository leak check still found one Kaggle path before that notebook was staged for untracking. Full `scripts/check.ps1` was interrupted while producing no output. `pytest.ini` now limits discovery to root `tests/` to avoid collecting nested checkout copies.
- Decisions and assumptions: The supplied design request supersedes the earlier two-mode-only dashboard presentation requirement for this step. Build the requested navigation in Streamlit, keep existing backend/API and model processing, and omit the Next.js prototype and GIS export.
- Remaining work / exact stopping point: Implement functional sidebar navigation and the requested central workspace/map layout, then rerun targeted tests and the mandatory check, inspect staged paths for secrets/prohibited files, finalize this log, and attempt commit/push without force.

## [2026-11-01 14:08] Step P21 follow-up: Unified Streamlit workspace and verification outcome
- Status: PARTIAL
- Files created or modified: `.gitignore`, `app.py`, `pytest.ini`, `scripts/check_leaks.py`, `tests/test_app_smoke.py`, `tests/test_leaks.py`, `tests/test_navigation.py`, `tests/test_panel_analyze.py`, `ui/navigation.py`, `ui/panel_analyze.py`, `ui/state.py`, `ui/theme.py`, `DEVELOPMENT_LOGS.md`; staged removals of nested duplicate app trees, the Next.js prototype, and tracked model/training artifacts.
- Summary of work completed (3–8 lines):
  - Rebuilt the root Streamlit shell with the requested branded function sidebar, project details in the center workspace, and a persistent map beside it. Sidebar destinations cover mission control, analysis, live demo, map, image processing, attack lab, forensics, audit logs, model evaluation, and system details.
  - Connected the function views to existing backend analysis, API events, ONNX evidence, local attack simulation, map overlays, and forensic packet evidence. When `TP_API_URL` is set, the dashboard no longer loads a second local model.
  - Removed the tracked nested project copies and static Next.js prototype. Untracked the protected local model/training files while preserving their local copies; the leak checker now excludes staged deletions from the final-tree scan.
  - Corrected a pre-existing backend routing test that passed an Ed25519 key as a positional sensor identifier instead of `sk`.
- Commands executed and test results: Focused checks passed: 22 tests, leak check, language check, Python compilation, `git diff --check`, and collection of 252 root tests. `scripts/check.ps1` was started but produced no output for 120 seconds and was stopped; AppTest and local Streamlit rendering could not be verified in this sandbox. A direct local HTTP request to a test Streamlit port was denied by socket permissions.
- Decisions and assumptions: Implement the supplied visual design as a single Streamlit application with workspace destinations rather than reintroducing the excluded Next.js app. No GIS export feature was added. Local sample/model data remains on disk but is excluded from Git.
- Remaining work / exact stopping point: Run `scripts/check.ps1` and open the root `app.py` dashboard on the user's Windows machine to verify the visual shell and route interactions. The P21 change still needs its git commit/push; remote `main` was previously ahead and rejected pushes, so preserve history and do not force-push.

## [2026-11-01 14:09] Step P21 follow-up: Commit and push outcome
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Committed P21 as `b1f1587` (`P21: Unify Streamlit dashboard workspaces`).
  - The push was rejected because `origin/main` contains commits that are not present locally.
  - Kept the local commit; no force-push or credential changes were made.
- Commands executed and test results: `git commit` succeeded. `git push origin main` failed with “fetch first”.
- Decisions and assumptions: Preserve remote history and synchronize before pushing.
- Remaining work / exact stopping point: Run `git pull --rebase origin main`, resolve any conflicts, then push. Restart the root Streamlit app from the project directory to view the updated interface; run the full check on the user's Windows environment because local socket access blocked AppTest here.

## [2026-11-01 14:14] Step P22: Restore the original Trust the Pixel visual design
- Status: PARTIAL
- Files created or modified: `app.py`, `assets/logo.svg`, `ui/navigation.py`, `ui/theme.py`, `ui/panel_analyze.py`, `tests/`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Started from the user's correction that the recent dashboard does not match the screenshots.
  - Located the original lime-and-cyan Trust the Pixel logo and Streamlit theme in the preceding Git revision; the screenshots' design references the same palette and sidebar system.
  - Identified a widget-state ordering issue in the Attack Lab flow: processing updates image-layer widget keys after those widgets have already been instantiated.
- Commands executed and test results: Read-only inspection of prior Git revisions completed. No code changes or checks for P22 have run yet.
- Decisions and assumptions: Restore the old design in the existing Streamlit app; do not restore the Next.js prototype. Keep live API/model state and avoid placeholder metrics.
- Remaining work / exact stopping point: Restore the old logo/theme, rework the header/sidebar layout to match the screenshots, fix Attack Lab widget ordering, add regression coverage, then run focused and required checks and complete the Git workflow.

## [2026-11-01 15:02] Step P22 resumed: Restore the screenshot design and correct Attack Lab widget order
- Status: PARTIAL
- Files created or modified: `app.py`, `assets/logo.svg`, `tests/test_navigation.py`, `ui/navigation.py`, `ui/panel_analyze.py`, `ui/theme.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Restored the historic Trust the Pixel lime-and-cyan logo, grouped function sidebar, branded top bar, ground-station indicator, and workspace header in the Streamlit app.
  - Kept the analysis view beside the map and moved the Analyze area / Live monitor control into the analysis workspace.
  - Corrected invalid/unsupported sidebar Material icon names and expanded navigation coverage for Copernicus acquisition/configuration and verification.
  - Moved Attack Lab controls before keyed map-layer widgets so processing does not modify Streamlit widget state after instantiation.
- Commands executed and test results: `tests/test_navigation.py` passed (2 tests); the configured-backend analysis test passed (1 test); Python compilation and `git diff --check` passed; leak and language checks passed. The AppTest panel suite stalled and was interrupted in this sandbox. `scripts/check.ps1` produced no output while its full pytest run was active and was interrupted; full suite and visual browser verification remain incomplete.
- Decisions and assumptions: Recreate the screenshot design in the existing Streamlit app; continue excluding the Next.js prototype and GIS export. Dynamic service status comes from the configured runtime context; do not substitute hardcoded online metrics.
- Remaining work / exact stopping point: Verify the app in the user's local browser and run `scripts/check.ps1` in the Windows environment where Streamlit AppTest can access local sockets. Do not stage the unrelated untracked `kernel_figure.png`.

## [2026-11-01 15:08] Step P22 commit and push outcome
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Committed the P22 visual restoration as `6b1782d` (`P22: Restore original Trust the Pixel design`).
  - The untracked `kernel_figure.png` was left untouched.
  - Attempted `git push origin main`; it produced no output for approximately 20 seconds and was interrupted, so publication is unconfirmed.
- Commands executed and test results: `git add` and `git commit` succeeded after obtaining repository index access. `scripts/check.ps1` was retried and stalled again in the full pytest run; it was interrupted. Focused navigation/backend tests and static checks are recorded above.
- Decisions and assumptions: No force push, credential changes, or history rewrite was attempted.
- Remaining work / exact stopping point: Run the full checks locally and verify the interface in a browser. Check `git status` and `git push origin main` to confirm/publish the local commit when the remote is reachable.

## [2026-11-01 15:15] Step P23: Fix Windows PROJ database selection for area analysis
- Status: PARTIAL
- Files created or modified: `tp/sentinel_live.py`, `tests/test_geo.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Reproduced the user's area-analysis `CRSError` in the project virtual environment.
  - Confirmed the process environment points PROJ_LIB at an incompatible PostGIS database whose layout version is too old for Rasterio.
  - Configure the process to use the `proj.db` shipped with its installed Rasterio package before Sentinel coordinate transformations.
  - Added a regression assertion that the runtime selects Rasterio's bundled PROJ database; existing geospatial tests exercise footprints, reprojection, and chip reading.
- Commands executed and test results: Before the fix, `tests/test_geo.py` failed 4 CRS-dependent tests with `proj.db ... DATABASE.LAYOUT.VERSION.MINOR = 2 whereas a number >= 6 is expected`. After the fix and regression assertion, `tests/test_geo.py` passed (8 tests); Python compilation, `git diff --check`, leak check, and language check passed. `scripts/check.ps1` stalled in the full test run without output and was interrupted. Live Planetary Computer access and full Streamlit flow were not run in this sandbox.
- Decisions and assumptions: Rasterio's bundled PROJ data is the compatible runtime source; override only the current Python process environment, not machine-wide settings.
- Remaining work / exact stopping point: Verify live area analysis after restarting Streamlit in the user's environment. Confirm whether the P23 commit reached the remote; do not stage unrelated `kernel_figure.png`.

## [2026-11-01 15:18] Step P23 commit and push outcome
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Committed the PROJ database fix as `920a726` (`P23: Fix bundled PROJ data for area analysis`).
  - Attempted `git push origin main`; it produced no output for approximately 15 seconds and was interrupted, so publication is unconfirmed.
- Commands executed and test results: Commit succeeded. Geospatial regression tests passed (8); the required full check stalled in pytest, as recorded above.
- Decisions and assumptions: No force push or credential changes were attempted.
- Remaining work / exact stopping point: Restart Streamlit in the user's environment and retry live area analysis. Check `git status` and push the local P23 commit when the remote is reachable.

## [2026-11-01 15:25] Step P24: Clarify backend setup and retry unusable CRS scenes
- Status: PARTIAL
- Files created or modified: `app.py`, `ui/panel_analyze.py`, `tests/test_panel_analyze.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Added System details guidance when the backend URL or source signing key is missing, including the distinction between an unconfigured URL, an unavailable API, and an untrusted key.
  - Added an analysis-panel notice when the dashboard is using local inference because no API URL is configured.
  - Live area processing now skips candidate scenes with invalid CRS metadata and tries the next acquisition; if none work, it shows a clear scene/CRS message.
  - Added focused regression coverage for the alternate-scene path.
- Commands executed and test results: Focused CRS, alternate-scene, and navigation tests passed (11 tests); compilation, `git diff --check`, leak check, and language check passed. The required `scripts/check.ps1` stalled during its full pytest run and was interrupted. No live API or Copernicus request was possible from this sandbox.
- Decisions and assumptions: The screenshot shows API URL and source key are absent in the Streamlit process. Preserve runtime configuration via environment variables or Streamlit secrets; do not embed a backend URL or credential.
- Remaining work / exact stopping point: Set `TP_API_URL` and `TP_SOURCE_PRIVATE_KEY` for the Streamlit process, keep the backend server running, restart Streamlit, and verify area analysis at points with alternate scenes. Synchronize the local branch with remote `main` before pushing; do not stage unrelated `kernel_figure.png`.

## [2026-11-01 15:28] Step P24 commit and push outcome
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Committed P24 as `09094c0` (`P24: Clarify backend setup and skip invalid CRS scenes`).
  - The normal push was rejected because remote `main` contains commits absent locally.
  - No force push or history rewrite was attempted.
- Commands executed and test results: `git commit` succeeded; `git push origin main` returned `fetch first`.
- Decisions and assumptions: Preserve remote history. Do not run a pull/rebase because the project Git rules list only add, commit, and push as allowed write operations.
- Remaining work / exact stopping point: Configure the Streamlit process and verify live area analysis; synchronize remote history under the repository's Git rules, then push the local commits.

## [2026-11-01 15:32] Step P25: Rename the product to earthLens
- Status: PARTIAL
- Files created or modified: `AGENTS.md`, `README.md`, `api.py`, `app.py`, `tests/test_map_view.py`, `ui/map_view.py`, `ui/navigation.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Updated the Streamlit page title, sidebar brand, workspace breadcrumb, map title, and FastAPI service title to earthLens.
  - Updated the project README and active project context to use the new name.
  - Kept existing Trust the Pixel / TP identifiers where they remain tied to protocol, model hosting, Python packages, test fixtures, and the current Git remote.
- Commands executed and test results: Map and navigation tests passed (9 tests); Python compilation, `git diff --check`, leak check, and language check passed. `scripts/check.ps1` stalled in its full pytest run without output and was interrupted.
- Decisions and assumptions: Rename the product-facing identity without renaming the Hugging Face model, API protocol fields, Python namespace, existing repository URL, or local project folder.
- Remaining work / exact stopping point: Confirm remote synchronization and publish the local commit when possible; do not stage unrelated `kernel_figure.png`. Full test suite remains incomplete due to the recurring stall.

## [2026-11-01 15:34] Step P25 commit and push outcome
- Status: PARTIAL
- Files created or modified: `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Committed the earthLens rename as `457e0dc` (`P25: Rename product to earthLens`).
  - Attempted `git push origin main`; it produced no output for approximately 15 seconds and was interrupted.
- Commands executed and test results: Commit succeeded; remote publication is unconfirmed. The full check remains stalled in pytest.
- Decisions and assumptions: No force push or credential changes were attempted.
- Remaining work / exact stopping point: Synchronize local `main` with the remote under the repository's Git rules, then push.

## [2026-11-01 15:38] Step P26: Document exact earthLens desktop setup
- Status: PARTIAL
- Files created or modified: `README.md`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Reworked the README around the current earthLens Streamlit dashboard, FastAPI backend, Hugging Face ONNX model, and image-integrity workflow.
  - Added separate PowerShell startup steps for provisioning the matching source keypair, running the API, and launching Streamlit with all three required settings.
  - Documented the expected health response and the exact service checks that should display Yes in System details.
  - Added troubleshooting for missing dashboard variables, API readiness, key trust, unusable area scenes, CRS startup, and offline data.
  - Removed stale prototype/GIS-export/Kali walkthrough content from the user-facing project README.
- Commands executed and test results: Leak check and language check passed; `git diff --check` passed. `scripts/check.ps1` stalled in its full pytest run without output and was interrupted. No private key contents or credentials were added to documentation.
- Decisions and assumptions: Use environment variables per PowerShell process for local desktop configuration; keep the actual repository clone URL as a user-supplied value until the GitHub destination is confirmed.
- Remaining work / exact stopping point: Reread the README and log entry, commit the documentation locally, and leave the GitHub push for the user as requested. The full test suite remains incomplete due to the recurring stall.

## [2026-11-01 15:45] Step P27: Add an earthLens attacker lab guide
- Status: PARTIAL
- Files created or modified: `attacker/README.md`, `README.md`, `tests/test_live_monitor_tools.py`, `DEVELOPMENT_LOGS.md`.
- Summary of work completed (3–8 lines):
  - Replaced the stale attacker guide with earthLens-specific instructions for a direct local feed and an isolated Kali reverse-proxy demonstration.
  - Documented the packet flow, scenario modes, attack families, host-only network setup, restricted firewall rule, feed commands, cleanup, and key-handling boundaries.
  - Corrected protocol details: the current proxy addon modifies JSON `/ingest`; TPX2 device feeds use `/ingest_v2` directly.
  - Linked the attacker guide from the root README.
  - Made the direct feed integration test explicitly configure its API URL instead of relying on the host shell environment.
- Commands executed and test results: Ten isolated scenario, device-scenario, menu, and session-recording tests passed; feed/device CLI help commands passed; leak, language, and diff checks passed. A broader run reached an API TestClient feed test and stalled; `scripts/check.ps1` also stalled in the full pytest run and was interrupted.
- Decisions and assumptions: The Kali procedure is restricted to a private host-only test network. The private signing key remains on Windows; no Kali or public target instructions are included.
- Remaining work / exact stopping point: Review the guide and log, commit the files locally, and leave GitHub publication to the user as requested. Full test suite remains unverified because the API TestClient run stalls in this environment.

## [2026-11-01 15:52] Step P28: Publish current earthLens snapshot to GitHub
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md (publish preparation).
- Summary of work completed (3–8 lines):
  - Confirmed the local branch is main and includes the current earthLens documentation and implementation commits.
  - Confirmed the working tree contains one unrelated untracked image; it will not be published.
  - Found prohibited model notebooks in earlier commits, so the existing commit history cannot be pushed safely.
  - Planned publication as a fresh snapshot containing only files tracked at the current commit.
  - The destination-ref check could not reach GitHub because network access is restricted in this environment.
- Commands executed and test results: The destination git ls-remote attempt failed before contacting GitHub (DNS/network thread startup error).
- Decisions and assumptions: Preserve the destination repository's existing history; do not force-push. Use a clean snapshot and only proceed if remote state can be verified.
- Remaining work / exact stopping point: Run the required project check, obtain an approved network-enabled remote-ref check, then push the safe snapshot to main if the destination permits a normal push.


## [2026-11-01 15:55] Step P29: Add earthLens to the existing GitHub main branch
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md (publish status).
- Summary of work completed (3–8 lines):
  - Confirmed the GitHub destination already has an initial commit on main.
  - Cloned the destination into a temporary directory to preserve its existing history and prepare a normal fast-forward update.
  - The source repository's .git metadata is read-only in this workspace, so a local source commit cannot be created here.
  - The required scripts/check.ps1 run produced no output for 30 seconds and was stopped; full tests remain unverified.
  - Preparing a snapshot from current tracked source files, excluding untracked files and protected artifacts.
- Commands executed and test results: Remote git ls-remote succeeded and reported an existing main ref; scripts/check.ps1 stalled without output and was interrupted; source git commit was blocked by the workspace's read-only Git metadata.
- Decisions and assumptions: Commit and push from the temporary clone, whose history starts at the existing remote commit; never force-push or include the source branch's prohibited historical notebooks.
- Remaining work / exact stopping point: Validate the snapshot, commit it in the temporary clone, and attempt a normal push to main. Record the actual push result and final status.


## [2026-11-01 15:58] Step P30: Record earthLens GitHub publication
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Pushed the current tracked earthLens project snapshot to the existing GitHub main branch as commit 4226e16.
  - Preserved the existing remote initial commit with a normal fast-forward push; no force push was used.
  - Excluded prohibited directories, key files, model artifacts, and the unrelated untracked image from the published snapshot.
  - Leak and language checks passed against the committed snapshot.
  - The complete scripts/check.ps1 suite remains unverified because it stalled without output and was interrupted.
- Commands executed and test results: Push succeeded (7b4783..4226e16 main -> main); leak check passed; language check passed; full project check stalled after 30 seconds with no output.
- Decisions and assumptions: Use a clean snapshot based on the destination's existing main branch because the source history includes prohibited historical notebooks.
- Remaining work / exact stopping point: GitHub contains the published snapshot. Full test verification remains outstanding; the source repository's Git metadata is read-only here, so the log correction will be committed and pushed from the temporary clone.


## [2026-11-01 15:58] Step P31: Confirm publication and record stopping point
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Confirmed the final publication log update was committed as 142980 and pushed to the GitHub main branch.
  - The published project snapshot remains based on the destination's original commit and contains no prohibited paths.
  - Leak and language checks passed after the final log update.
  - Full test-suite verification remains incomplete because scripts/check.ps1 stalled without output.
- Commands executed and test results: Final log push succeeded (4226e16..b142980 main -> main); leak check passed; language check passed; full suite remains unverified.
- Decisions and assumptions: No force push or credential changes were used.
- Remaining work / exact stopping point: The requested project is published at https://github.com/trustthepixel/EarthLens on main; run the full test suite in an environment where it completes.


## [2026-11-01 16:00] Step P32: Clarify final remote commit record
- Status: PARTIAL
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - The final GitHub main branch commit is 01b2e6035e0818f00ce0a8ee125adc1e69e9f75b.
  - This entry clarifies the final commit reference in the preceding publication log entry.
  - The project snapshot was published without protected paths or the unrelated untracked image.
  - Leak and language checks passed; the complete check script did not finish in this environment.
- Commands executed and test results: The previous push returned success; a separately approved remote-ref check confirmed the commit hash above.
- Decisions and assumptions: Preserve the existing remote history; no force push or credential changes.
- Remaining work / exact stopping point: Push this final log clarification as a fast-forward. The full test suite remains unverified.
