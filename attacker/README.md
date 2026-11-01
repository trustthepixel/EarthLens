# EARTHLENS Attack Lab

The `attacker/` tools generate controlled test packets and, optionally, modify those packets in an isolated proxy lab. They let you see how the EARTHLENS ground station handles changes to image pixels, signed metadata, signatures, and replayed packets.

This lab is for the project's prepared sample chips and a ground-station API that you operate. It does not attack Copernicus, access satellite communications, or authorize testing other systems. The scenario name sent with a packet is a sender-provided label, not proof that the named change occurred.

For dashboard installation, API setup, and the three configured-service checks, see the root [EARTHLENS README](../README.md). This guide assumes the model is ready, the local source keypair is provisioned, and the API trusts its matching public key.

## Packet flow

```text
Prepared sample chip
        │
        ▼
Windows feed signs packet ──► optional Kali proxy alters test packet ──► EARTHLENS API
                                                                               │
                                                                               ▼
                                                                  verification and ONNX result
                                                                               │
                                                                               ▼
                                                                  Streamlit Live monitor
```

The normal feed keeps the private source key on Windows. The proxy receives signed packets and changes them according to the selected scenario. The API reports its verification and model result to the dashboard. Keep private keys and model files out of the proxy VM.

## Option A: Run a local feed without Kali

This is the simplest way to check that the API and dashboard receive feed events. Start the API and Streamlit as described in the root README. In a third PowerShell window in the project folder, set the API URL and send three prepared packets:

```powershell
$env:TP_API_URL = "http://127.0.0.1:8000/health"
.\.venv\Scripts\python.exe -m attacker.feed --direct --places Beja --interval 4 --count 3
```

Open **Live demo** or **Live monitor** in the dashboard to see the incoming events. The feed reads prepared chips from the project's local data and signs them with `keys/source_private.pem`. Stop a continuous feed with Ctrl+C.

## Option B: Use the isolated Kali proxy

### 1. Create a host-only VM network

The example below assumes a VirtualBox host-only network:

| Device | Example address |
| --- | --- |
| Windows host | `192.168.56.1` |
| Kali VM | `192.168.56.101` |
| Host-only subnet | `192.168.56.0/24` |

Use a Host-only Adapter for Kali's lab connection. Do not use a bridged adapter. If the VM needs Internet briefly to install packages, enable a separate NAT adapter for setup and disable it before the lab. Confirm the host-only address in Kali with `ip -4 -br addr`.

### 2. Start the Windows API for the host-only lab

The API needs to listen on the Windows host-only interface so Kali can reach it. In a PowerShell window in the project folder, set the model repository and start Uvicorn:

```powershell
$env:HF_MODEL_REPO = "trustthepixel/trust-the-pixel-detector"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000
```

Binding to `0.0.0.0` exposes the API on the host's network interfaces. Keep the VM on the private host-only network and, if Windows Firewall requires a rule, restrict TCP port 8000 to `192.168.56.0/24`:

```powershell
New-NetFirewallRule -DisplayName "EARTHLENS host-only API" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress 192.168.56.0/24
```

Keep the API terminal open. Check `http://127.0.0.1:8000/health` from Windows and confirm `ok` is `True` and `trusted_keys` is at least `1`. The dashboard should use the Windows host-only URL for this setup; configure its `TP_API_URL` as `http://192.168.56.1:8000/health` in the Streamlit PowerShell window before starting Streamlit.

### 3. Copy the proxy code to Kali

In Kali, create a small lab directory and the two package folders:

```bash
mkdir -p ~/earthlens-lab/tp ~/earthlens-lab/attacker
```

From the Windows project folder, copy only the proxy's required source files. Replace `kali` if your VM uses another account name:

```powershell
scp .\tp\attacks.py .\tp\provenance.py kali@192.168.56.101:~/earthlens-lab/tp/
scp .\attacker\__init__.py .\attacker\scenarios.py .\attacker\mitm_addon.py .\attacker\places.json .\attacker\requirements.txt kali@192.168.56.101:~/earthlens-lab/attacker/
```

Do not copy `keys/`, `trusted_keys/`, the model directory, `.env`, or any PEM file to Kali.

### 4. Install and start the reverse proxy

In Kali Terminal 1:

```bash
cd ~/earthlens-lab
python3 -m venv .venv-proxy
source .venv-proxy/bin/activate
python -m pip install --upgrade pip
python -m pip install -r attacker/requirements.txt
export PYTHONPATH="$PWD"
mitmdump --listen-host=0.0.0.0 --mode=reverse:http://192.168.56.1:8000 -p 8080 -s attacker/mitm_addon.py
```

Leave the proxy running. It forwards requests to the Windows API and exposes a lab control route at `/__mode`. Keep the Kali VM attached to the host-only network for the demonstration.

### 5. Select a scenario

In Kali Terminal 2, use the same project directory and environment:

```bash
cd ~/earthlens-lab
source .venv-proxy/bin/activate
export PYTHONPATH="$PWD"
export TP_PROXY_URL=http://192.168.56.101:8080
python -m attacker.attack_menu
```

The menu asks for a mode, attack family, severity, target place, and probability. Use **Back to normal (passthrough)** to disable changes. A place-targeted scenario applies to packets whose signed coordinates are within 30 km of that place; `all` applies to every packet.

Available modes:

| Mode | Demonstration |
| --- | --- |
| `passthrough` | Forward the packet unchanged. |
| `pixels` | Change pixels but retain the original signed metadata. |
| `manifest_meta` | Change signed scene metadata. |
| `manifest_rehash` | Change pixels and update their hashes without a valid source signature. |
| `resign` | Re-sign changed pixels with a different, untrusted demonstration key. |
| `replay` | Replay a packet from the current proxy session. |
| `strip` | Remove the source signature. |
| `stolen_key` | Special case that requires a deliberately configured test key; leave disabled for ordinary demonstrations. |

Pixel families include `inpaint_ns`, `copy_move`, `spectral`, `photometric`, `band_shift`, `texture`, `compound`, and `compound_mixed`. Severity options are `subtle`, `medium`, and `strong`.

### 6. Send packets through the proxy

In a Windows PowerShell window, send a short Beja feed through the Kali proxy:

```powershell
.\.venv\Scripts\python.exe -m attacker.feed --url http://192.168.56.101:8080/ingest --places Beja --interval 4 --count 3
```

Watch **Live monitor** in EARTHLENS. The API records its computed verification and model evidence. `assumed_mode` and `X-Attack-Mode` are supplied by the test feed/proxy and are labels only.

### 7. Stop and reset

Stop the Windows feed, the proxy, and the API with Ctrl+C in their respective terminals. Before the next run, select passthrough in the menu or restart the proxy, which starts in passthrough mode. Restarting the API resets its in-memory replay state; use the project's API reset behavior only with test data.

## Tool reference

- `attacker.feed`: repeatedly sends signed prepared image packets to the API (`--direct`) or a proxy (`--url`).
- `attacker.source_send`: sends one signed prepared packet to the API.
- `attacker.attack_menu`: configures the running proxy through its `/__mode` control route.
- `attacker.mitm_addon`: applies scenarios to JSON requests sent to `/ingest`.
- `attacker.run_scenarios`: runs a campaign against the API or proxy and writes a local `attack_campaign.csv` report.
- `attacker.device_feed` and `attacker.device_scenarios`: generate and alter TPX2 binary test packets. The current mitmproxy addon handles the JSON `/ingest` route; use the device feed directly with `/ingest_v2` for TPX2 demonstrations.

Generated packet counters, chain state, event data, previews, and campaign reports are local test artifacts. Do not commit those artifacts or any source/device private keys.
