# Offline Operation & Network-Isolation Verification Procedure

**Milestone:** GitHub Issue #1 (`test/offline-verification`)
**Status:** Physical Offline Verification Recorded (October 18, 2026)
**Target Repository:** `TechGenDM/Air-Gapped-RAG`
**Base Commit:** `c3ef318a31faee103cf41b2d6aac1c73b4b90db9`

---

## 1. Scope & Objective

The objective of **GitHub Issue #1** is to establish reproducible evidence
for offline operation and network-isolation behavior in Air-Gapped RAG.

This document defines:
1. The boundary between verified local application functionality and pending
   network-isolation verification.
2. An audit of observed network connections during local execution.
3. A review of Ollama runtime options and their relationship to network
   isolation.
4. A step-by-step, reproducible manual verification procedure for human
   maintainers on a physical host with external connectivity severed.
5. The recorded empirical test results from a completed physical-host offline
   verification.
6. The conclusions, scope, and ongoing testing limitations.

---

## 2. Status Distinctions & Technical Boundaries

To maintain rigorous transparency, this project strictly distinguishes
between four categories of claims:

### A. Verified Local Application Functionality

The following properties have been verified through code inspection and
automated testing in the local development environment:

* **Application Architecture:** The application code (`backend/app/` and
  `frontend/src/`) is configured to communicate with local services over
  loopback addresses (`http://127.0.0.1:8000` for FastAPI and
  `http://127.0.0.1:11434` for Ollama). It does not integrate third-party
  cloud AI APIs (such as OpenAI, Anthropic, or Google Cloud) for inference.
* **Embedded Processing:** PDF text parsing and optical character recognition
  (OCR) execute locally via PyMuPDF and system Tesseract (`tesseract 5.5.2`).
  Vector storage is embedded in-process on the local disk using LanceDB
  (`backend/data/lancedb/`).
* **Functional Test Invariants:** The automated test suite (75 backend
  unit/integration tests) and the synthetic contract demonstration script
  (`scripts/demo_air_gapped_rag.py --local`) pass in the local environment,
  validating:
  - Multi-page PDF text extraction.
  - Tesseract OCR table reconstruction.
  - Page-preserving sliding chunking.
  - Local dense vector generation via Ollama `/api/embed`.
  - Evidence-grounded generation with physical page citations via Ollama
    `/api/chat`.
  - Safe abstention (`"Not found in records"`, `evidence_sufficient=False`,
    `sources=[]`) when evidence is absent.

These tests confirm that the application's own code paths communicate over
loopback. They do not rule out outbound traffic from runtime dependencies,
background daemons, or the operating system itself.

### B. Observed Outbound Socket

During a live socket audit of running processes
(`lsof -i -P -n | grep -E 'python|node|ollama'`), an established outbound
TCP connection was observed originating from the Ollama daemon process:

```text
ollama  2262  devasishmishra  10u  IPv4  0xb722fe1dada123ce  0t0  TCP 192.168.31.200:49439->34.36.133.15:443 (ESTABLISHED)
```

**What is confirmed by observation:**
* The process `ollama` (PID 2262) held an established TCP connection to
  destination IP `34.36.133.15` on port `443` (HTTPS).
* WHOIS lookup of `34.36.133.15` shows it is within the `GOOGL-2` netblock
  (`34.4.5.0 – 34.63.255.255`), registered to Google LLC and designated for
  Google Cloud customer use.
* Reverse DNS resolves `34.36.133.15` to
  `15.133.36.34.bc.googleusercontent.com` (a generic Google Cloud reverse
  pointer).
* Forward DNS lookup of `ollama.com` resolves to `34.36.133.15` at the time
  of testing, matching the observed destination.
* Forward DNS lookup of `registry.ollama.ai` resolves to different IPs
  (`104.18.16.170`, `104.18.17.170`) and does **not** match the observed
  destination.

**What the Python backend and Node frontend showed:**
* Neither process showed outbound WAN sockets; their sockets were strictly
  bound to `127.0.0.1` or local IPC. This is consistent with their
  application code, but does not constitute proof that they will never
  produce outbound traffic under all conditions.

### C. Unconfirmed: Connection Destination & Purpose

* The forward DNS match (`ollama.com` → `34.36.133.15`) is consistent with
  Ollama contacting its own website or API endpoint, but DNS mappings can
  change and a single-point-in-time lookup is not definitive proof of what
  hostname the TLS handshake targeted.
* Community documentation and release discussions suggest that Ollama may
  contact its public servers on startup or during CLI interactions for
  purposes such as version checks, update polling, or model registry
  metadata.
* **Caution:** Because deep packet inspection (e.g. via Wireshark, `mitmproxy`,
  or TLS session key logging) was not conducted on this session, attributing
  this connection to a specific internal Ollama function (version check,
  telemetry, update polling, or other) is an **unconfirmed hypothesis**.
* The project records the empirical fact of the connection and its network
  ownership without making unsupported assumptions about its hostname,
  purpose, or payload.

### D. Full Offline & Network-Isolation Verification (Physical Verification Recorded)

* Local-first execution (functioning without cloud LLM APIs) is distinct from
  verified physical air-gapped isolation.
* A controlled manual physical-host verification has now been performed and
  recorded on the designated test workstation (see Section 6: Completed Physical
  Offline Verification).
* Under the specific conditions tested (all external network paths severed,
  Ollama launched with `OLLAMA_NO_CLOUD=1`), the application performed PDF upload,
  indexing, grounded question answering with exact physical-page citations, safe
  abstention, and successive query handling without errors and with zero external
  sockets observed.
* While this establishes reproducible empirical evidence of offline operation
  on the tested host, it does not constitute universal security guarantees across
  every possible hardware configuration, network topology, or dependency update.

---

## 3. Ollama Configuration & Network Isolation Review

Ollama serves as the local engine for embeddings (`nomic-embed-text`) and
answer generation (`gemma4:12b`). Configuring Ollama for restricted network
environments requires understanding its supported flags and their limits.

### Review of Documented Environment Variables

Inspection of the official Ollama CLI (`ollama serve --help`, version
`0.35.1`) identifies the following relevant variables:

* `OLLAMA_HOST` — Configures the IP and port for the Ollama server
  (default `127.0.0.1:11434`).
* `OLLAMA_NO_CLOUD` — Disables Ollama cloud features, specifically
  described as "remote inference and web search."
* `OLLAMA_ORIGINS` — Comma-separated list of allowed HTTP request origins.
* `OLLAMA_MODELS` — Path to the local model weights directory.

### Critical Clarifications

1. **`OLLAMA_NO_TELEMETRY` is not documented:** The environment variable
   `OLLAMA_NO_TELEMETRY` does not appear in `ollama serve --help` output
   (version `0.35.1`) and is not listed in Ollama's official documentation.
   It should not be relied upon or recommended without first verifying
   support in the specific Ollama release being used.

2. **`OLLAMA_NO_CLOUD` is not a general network-egress blocker:** Setting
   `OLLAMA_NO_CLOUD=1` disables the specific cloud features Ollama
   describes (remote inference and web search). It does **not** claim to
   prevent all outbound network activity. Other connections (such as
   registry checks, version polling, or DNS lookups) may still occur even
   with this flag set. However, running with `OLLAMA_NO_CLOUD=1` under
   severed network interfaces produced clean local execution without
   errors or active WAN sockets.

3. **Network isolation requires hardware or OS-level enforcement:** In an
   air-gapped or high-security context, software configuration flags alone
   are insufficient. Outbound network traffic must be blocked at the OS
   layer (firewall rules via `pf` / `iptables` / `nftables`), container
   network namespace level (e.g. Docker `--network none`), or physical
   layer (disabled network adapters or unplugged cables).

---

## 4. Pre-requisite Preparation (Online State)

Before disconnecting from the internet, all software packages, model
weights, and linguistic assets must be pre-installed and cached locally on
the host machine.

```bash
# 1. Verify Ollama Model Cache
ollama list
# Expected: nomic-embed-text:latest and gemma4:12b present in local cache

# 2. Verify Backend Virtual Environment & Dependencies
cd backend
source .venv/bin/activate
uv run pytest -q
# Expected: 75 passed

# 3. Verify Frontend Bundles
cd ../frontend
pnpm run build
# Expected: Successful production build
```

---

## 5. Step-by-Step Manual Disconnected Test Procedure

> [!WARNING]
> **Do NOT run network severance commands inside a remote agent, SSH
> session, or cloud IDE.** Disabling network adapters will instantly sever
> the connection. This procedure must be performed directly on the physical
> host machine by a human operator.

### Step 0: Record Baseline Network Configuration

Before disabling any interfaces, record the current network state so it can
be restored accurately afterward:

```bash
# macOS — identify all hardware ports and their current status
networksetup -listallhardwareports
networksetup -listallnetworkservices

# Record the Wi-Fi interface name (may not be en0 on all Macs)
WIFI_IFACE=$(networksetup -listallhardwareports \
  | awk '/Wi-Fi/{getline; print $2}')
echo "Wi-Fi interface: $WIFI_IFACE"

# Record current Wi-Fi power state
networksetup -getairportpower "$WIFI_IFACE"

# Record active network interfaces, IP addresses, and default routes
ifconfig | grep -E '^[a-z]|inet '
netstat -rn -f inet | head -20
scutil --nwi

# Check for active VPN connections
ifconfig | grep -E '^(utun|ppp|ipsec|tun)[0-9]'
scutil --nc list 2>/dev/null | grep -i connected

# Linux — equivalent commands
# ip link show
# ip addr show
# ip route show
# nmcli connection show --active
```

Save this output to a file for later comparison.

### Step 1: Sever External Network Connectivity

Disable all external network paths. This requires identifying and disabling
each active connection type individually.

**Identify the Wi-Fi interface (macOS):**
The Wi-Fi device is not always `en0`. Use the output from Step 0:
```bash
# Use the interface identified in Step 0
WIFI_IFACE=$(networksetup -listallhardwareports \
  | awk '/Wi-Fi/{getline; print $2}')
```

**Disable Wi-Fi:**
```bash
# macOS
networksetup -setairportpower "$WIFI_IFACE" off

# Linux
sudo nmcli radio wifi off
```

**Disconnect Ethernet:** Physically unplug all Ethernet cables. If using a
USB-C or Thunderbolt dock with Ethernet, disconnect the dock or the cable.

**Disconnect VPN:** If any VPN profiles are active, disconnect them:
```bash
# macOS — list and disconnect VPN connections
scutil --nc list 2>/dev/null
# For each connected VPN:
# scutil --nc stop "VPN Name"

# Linux
# sudo nmcli connection down <vpn-connection-name>
```

### Step 2: Verify Network Disconnection

A failed ICMP ping alone is not sufficient evidence of complete network
isolation. ICMP may be blocked by firewalls even on connected networks, and
a single probe cannot detect all connectivity paths (e.g. a VPN tunnel or
a secondary Ethernet adapter may remain active).

Run the following checks and interpret them **together**:

```bash
# 2a. Verify Wi-Fi is powered off
networksetup -getairportpower "$WIFI_IFACE"
# Expected: "Wi-Fi Power (en0): Off" (or the identified interface)

# 2b. Verify no active non-loopback interfaces have IP addresses
ifconfig | grep -B2 'inet ' | grep -v '127.0.0.1' | grep -v '::1'
# Expected: No inet addresses on physical interfaces, or only
# link-local (169.254.x.x) / unconfigured interfaces

# 2c. Verify no default route exists
netstat -rn -f inet | grep '^default'
# Expected: No output (no default gateway)

# 2d. Verify no VPN tunnels are active
ifconfig | grep -E '^(utun|ppp|ipsec|tun)[0-9]'
# Expected: No output, or listed interfaces show no inet address

# 2e. Attempt ICMP connectivity to a public IP (no DNS required)
ping -c 1 -W 2 8.8.8.8
# Expected: "No route to host" or 100% packet loss

# 2f. Attempt DNS resolution
dig +short +timeout=2 registry.ollama.ai A
# Expected: Empty output or timeout

# 2g. Attempt HTTPS connectivity
curl -s --max-time 3 https://ollama.com
# Expected: Connection failure or timeout
```

**Interpretation:** No single check above is conclusive on its own. For
example, ping can fail due to firewall rules on a connected network, and
DNS can fail due to misconfigured resolvers. However, if **all** of the
following hold simultaneously, network isolation is established with
reasonable confidence:
- Wi-Fi reports powered off.
- No non-loopback interface has a routable IP address.
- No default route exists.
- No VPN tunnel interfaces are active.
- ICMP, DNS, and HTTPS probes all fail.

If any check produces an unexpected result (e.g. a VPN tunnel still holds
an IP, or curl succeeds), investigate and resolve before proceeding.

### Step 3: Stop Existing Ollama Instances and Start Clean

Ensure only one Ollama server process is running, and that it receives the
intended environment configuration. The macOS Ollama.app may auto-launch a
background instance.

```bash
# Kill any existing Ollama server processes
pkill -f 'ollama serve' || true
# On macOS, also quit the Ollama menu bar app if running
osascript -e 'quit app "Ollama"' 2>/dev/null || true

# Wait briefly for processes to exit
sleep 2

# Verify no Ollama process is still running
pgrep -fl ollama
# Expected: No output

# Start Ollama with cloud features disabled, bound to loopback
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ollama serve
```

Note: `OLLAMA_NO_CLOUD=1` disables Ollama's cloud inference and web search
features. It is **not** a general outbound network blocker. With network
hardware disabled in Step 1, outbound connections will fail at the OS level
regardless of this flag, but including it ensures cloud features are also
logically disabled.

### Step 4: Start Application Services

In separate terminal windows:

```bash
# Terminal 2 — Backend API
cd backend
source .venv/bin/activate
uvicorn app.main:app --port 8000
```

```bash
# Terminal 3 — Frontend
cd frontend
pnpm run start --port 3000
```

### Step 5: Verify Local Loopback Health

In a new terminal window, confirm that local processes respond over
`127.0.0.1`:

```bash
curl -s http://127.0.0.1:11434/api/tags | grep -o "gemma4:12b"
# Expected: gemma4:12b

curl -s http://127.0.0.1:8000/health
# Expected: {"status":"ok","app":"air-gapped-rag-backend","version":"0.1.0"}
```

### Step 6: Execute In-Process Automated Synthetic Demonstration

Verify the RAG pipeline end-to-end without UI clicks:

```bash
backend/.venv/bin/python scripts/demo_air_gapped_rag.py --local
```

**Verification Invariants:**
* Synthetic PDF generation succeeds.
* Chunking and LanceDB vector indexing complete.
* Queries 1–3 return substantive answers citing exact physical pages.
* Queries 4–5 return strict abstention (`"Not found in records"`,
  `evidence_sufficient=False`, `sources=[]`).

### Step 7: Execute Browser-Based UI Test

1. Open a local browser and navigate to `http://localhost:3000`.
2. Open Browser Developer Tools → **Network** tab.
3. Upload a sample contract PDF (under 50 MB).
4. Verify document viewer renders physical pages correctly.
5. Click **Index Document** and verify completion status.
6. Ask an in-document query; confirm answer and physical page citation.
7. Ask an out-of-document query; confirm safe refusal and zero citations.
8. Review the Developer Tools Network tab: check for any failed requests
   to external hosts. Record the full list of requested URLs.

### Step 8: Socket & Process Inspection

While application services are still running, audit all network sockets:

```bash
lsof -i -P -n | grep -E 'python|node|ollama'
```

**Verification Invariant:**
All sockets must reference `127.0.0.1` or `[::1]` only. No foreign IP
addresses should appear. If any external destination is listed, record the
full `lsof` line, the process name, PID, and destination, and note it as a
finding.

### Step 9: Check Ollama Logs for Connection Errors

Inspect the Ollama server output (from the terminal window in Step 3) for
any error messages related to failed outbound connections. Record these
messages — they provide evidence of what Ollama attempts when network
access is unavailable.

### Step 10: Restore Host Network Connectivity

Restore the network configuration recorded in Step 0:

```bash
# macOS — re-enable Wi-Fi using the identified interface
networksetup -setairportpower "$WIFI_IFACE" on

# Linux
sudo nmcli networking on
```

Reconnect Ethernet cables and VPN connections as needed. Verify restoration:

```bash
ping -c 1 8.8.8.8
# Expected: Successful reply
```

---

## 6. Completed Physical Offline Verification (October 18, 2026)

This section records the empirical results of the manual physical-host test
conducted in accordance with the procedure in Section 5.

### A. Test Environment & System Specifications

| Component | Recorded Value |
|---|---|
| **Date of Test** | October 18, 2026 |
| **Operator** | Repository Maintainer |
| **Host Hardware** | Apple Mac (Apple M4, 10-core CPU, 24 GB Unified Memory) |
| **Operating System** | macOS 27.0.1 (Darwin Kernel Version 27.0.0, arm64) |
| **Python Runtime** | Python 3.12.13 (in `backend/.venv`) via `uv` |
| **Node.js Runtime** | Node.js v25.8.0, pnpm 10.19.0 |
| **OCR Engine** | Tesseract 5.5.2 with English language pack |
| **Ollama Server** | Ollama version 0.35.1 |
| **Embedding Model** | `nomic-embed-text:latest` (ID: `0a109f422b47`, 274 MB, 768 dimensions) |
| **Generative LLM** | `gemma4:12b` (ID: `6114515d63c1`, 8.0 GB, `think: false`, `num_predict: 1024`) |
| **Vector Database** | Embedded LanceDB (disk-backed in `backend/data/lancedb/`) |

### B. Network Path Severance & Verification Checks

Before running application tests, all external connectivity was severed and
verified using the multi-probe procedure:

1. **Wi-Fi Interface Identification & Disconnection:**
   - Identified Wi-Fi device via `networksetup -listallhardwareports` as `en0`.
   - Disabled Wi-Fi via `networksetup -setairportpower en0 off`.
   - Verified state: `networksetup -getairportpower en0` reported `Wi-Fi Power (en0): Off`.
2. **Ethernet & Wired Interfaces:**
   - Physically unplugged all Ethernet cables and docks.
   - Verified that no wired interfaces (`en1`, `en2`, `en3`, `en4`, `bridge0`) held active routable IP addresses.
3. **VPN & Virtual Tunnels:**
   - Checked active VPN profiles via `scutil --nc list` and `ifconfig | grep -E '^(utun|ppp|ipsec|tun)[0-9]'`.
   - Confirmed zero active VPN connections or virtual tunnel interfaces.
4. **Interface IP Routing Check:**
   - Executed `ifconfig | grep -B2 'inet ' | grep -v '127.0.0.1' | grep -v '::1'`.
   - Result: No non-loopback interfaces had active routable IP addresses.
5. **Default Route Check:**
   - Executed `netstat -rn -f inet | grep '^default'`.
   - Result: Empty output (no default route configured).
6. **ICMP Connectivity Probe:**
   - Executed `ping -c 1 -W 2 8.8.8.8`.
   - Result: `ping: sendto: No route to host` (100% packet loss).
7. **DNS Resolution Probe:**
   - Executed `dig +short +timeout=2 registry.ollama.ai A`.
   - Result: Query timed out with empty output.
8. **HTTPS Egress Probe:**
   - Executed `curl -s --max-time 3 https://ollama.com`.
   - Result: Exited with error `curl: (28) Connection timed out` (no connection possible).

### C. Application Pipeline Verification Results

With all network paths severed, local services were started:
* Ollama: `OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ollama serve`
* Backend API: `uvicorn app.main:app --port 8000` (FastAPI)
* Frontend: `pnpm run start --port 3000` (Next.js)

The following verification steps were performed:

1. **Local Health Endpoints:**
   - `curl -s http://127.0.0.1:11434/api/tags` returned `gemma4:12b` and `nomic-embed-text:latest`.
   - `curl -s http://127.0.0.1:8000/health` returned `{"status":"ok","app":"air-gapped-rag-backend","version":"0.1.0"}`.
2. **PDF Upload & Text Extraction:**
   - Uploaded a sample contract agreement via the browser interface at `http://localhost:3000`.
   - Upload returned `201 Created` with generated UUID.
   - PyMuPDF successfully extracted digital text with 1-indexed physical page boundaries preserved.
   - Browser viewer rendered extracted page summaries and page preview cards.
3. **LanceDB Vector Indexing:**
   - Triggered document indexing via `POST /api/v1/documents/{id}/index`.
   - Vectorization executed over loopback via Ollama `/api/embed` using `nomic-embed-text`.
   - Chunks stored directly in local LanceDB table (`backend/data/lancedb/`).
4. **Evidence-Grounded Query & Page Citation:**
   - **Query:** *"What is the limitation of liability cap under Section 4?"*
   - **Answer Produced:** Correctly identified the $250,000 USD aggregate liability cap under Section 4.2.
   - **Citation Result:** Generated citation pill strictly referencing physical **Page 2**, matching the source contract.
   - **Evidence Sufficient:** `True`.
5. **Missing-Evidence Safe Refusal:**
   - **Query:** *"What is the statutory penalty for contract breach under Australian commercial law?"*
   - **Answer Produced:** `"Not found in records"`.
   - **Citation Result:** Zero citations generated (`sources=[]`).
   - **Evidence Sufficient:** `False`.
6. **Browser Successive-Question & Failure-State Behavior:**
   - Multiple questions asked consecutively in the UI without browser reload or service restart.
   - Each successive question correctly cleared prior answer text and citation pills while in-flight.
   - On intentional query error / empty submission, the UI displayed the error message and kept previous answers and citations cleared, preventing stale state.
7. **Wall-Clock Latency Measurements:**
   - Per-query click-to-render latency in the manual browser test was **not recorded**.
   - Reference baseline from automated in-process test runs: ~10s to ~27s per query depending on prompt length.

### D. Socket Audit During Active Test

While the backend, frontend, and Ollama were actively handling queries, the
socket audit command was executed:

```bash
lsof -i -P -n | grep -E 'python|node|ollama'
```

**Recorded Output:**
- `python` processes: bound strictly to `127.0.0.1:8000` (LISTEN) and loopback connections (`127.0.0.1:<port> -> 127.0.0.1:8000`).
- `node` processes: bound to `127.0.0.1` / `*:3000` (LISTEN) and internal IPC pairs (`127.0.0.1:49308 <-> 127.0.0.1:49309`).
- `ollama` process: bound strictly to `127.0.0.1:11434` (LISTEN) and loopback connections to the backend.
- **Unexpected External Sockets:** **0**. The previously observed outbound socket (`-> 34.36.133.15:443`) did not appear when running with `OLLAMA_NO_CLOUD=1` under severed network interfaces.
- **Ollama Error Logs:** No crash or fatal exit observed in Ollama logs when network access was unavailable; model inference proceeded entirely in local VRAM.

### E. Post-Test Restoration

After testing concluded:
- Restored Wi-Fi via `networksetup -setairportpower en0 on`.
- Verified restoration via `ping -c 1 8.8.8.8` (successful reply received).

---

## 7. Conclusions, Scope & Testing Limitations

1. **Scope of the Test:**
   - The test documented in Section 6 demonstrates that Air-Gapped RAG operates
     successfully without external network connectivity on the specific host,
     operating system, and model configuration tested (macOS 27.0.1, Apple M4,
     Ollama 0.35.1, Gemma 4 12B, nomic-embed-text).
   - All core capabilities—PDF ingestion, OCR, chunking, embedding, vector
     retrieval, physical page citation, safe refusal, and UI state management—
     functioned over loopback with zero external connections established.
2. **Explicit Limitations:**
   - **Environment-Specific:** This test confirms offline functionality on the
     particular workstation and software versions evaluated. It does not
     guarantee identical behavior on different platforms, Linux distributions,
     or container runtimes without independent verification.
   - **No Permanent Guarantee Against Third-Party Dependencies:** Future updates
     to third-party packages (Node modules, Python libraries, or Ollama releases)
     could introduce new network behaviors. Verification must be re-run whenever
     dependencies are updated.
   - **Software Flags vs. True Air-Gap:** Setting `OLLAMA_NO_CLOUD=1` disables
     cloud features, but software flags alone cannot guarantee network isolation
     if network interfaces remain active. True air-gap environments must enforce
     physical network severance or OS/firewall-level egress blocking.
   - **No Universal Security Claims:** This test does not evaluate or certify
     the system against side-channel analysis, physical memory extraction, or
     tampering with local model files.
3. **Milestone & Repository Tracking:**
   - This evidence satisfies the core technical milestone defined in GitHub
     Issue #1 (*Establish reproducible evidence for offline operation and
     network-isolation behavior*).
   - Issues #1 and #2 remain open pending final maintainer review and broader
     cross-platform evaluation.
   - The root `README.md` and privacy wording remain preserved as currently
     published until reviewed and approved.
