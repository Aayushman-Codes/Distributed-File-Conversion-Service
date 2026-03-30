# Distributed File Conversion Service (DFS)

A secure, multi-client distributed file conversion service using raw TCP sockets + SSL/TLS in Python, with a browser-based frontend.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        CLIENT SIDE                           │
│                                                              │
│   Browser ──HTTP──► web_server.py ──SSL/TCP──► server.py     │
│   client.py (CLI)  ──SSL/TCP──────────────────► server.py    │
│   tests/stress_test.py / benchmark.py                        │
└──────────────────────────────────────────────────────────────┘
                              │  TCP + SSL/TLS (port 9000)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                        SERVER SIDE                           │
│   server.py                                                  │
│   ├── Accept loop (main thread)                              │
│   ├── ClientHandler threads (1 per connection)               │
│   ├── JobScheduler (priority queue + worker pool)            │
│   │   └── converter.py (Pillow / pypdf / python-docx)        │
│   └── SSL Context (TLS 1.2+)                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Supported Conversions

| Input | Output Formats |
|-------|----------------|
| PNG | jpg, bmp, gif, webp, tiff |
| JPG / JPEG | png, bmp, gif, webp, tiff |
| BMP | png, jpg, gif, webp |
| GIF | png, jpg, bmp |
| WEBP | png, jpg, bmp |
| TIFF | png, jpg, bmp |
| JSON | csv, txt, xml |
| CSV | json, txt, xml |
| TXT | csv, json, xml |
| XML | csv, json, txt |
| PDF | txt, docx |
| DOCX | txt, pdf |

---

## Project Structure

```
project/
├── protocol.py        # Wire protocol, constants, framing helpers
├── server.py          # SSL TCP server + concurrent client handlers
├── scheduler.py       # Priority job queue + worker thread pool
├── converter.py       # All file conversion logic
├── client_lib.py      # Reusable DFSClient Python library
├── client.py          # Interactive CLI client
├── web_server.py      # HTTP bridge → serves frontend + API
├── frontend/
│   └── index.html     # Browser UI
├── certs/
│   ├── server.crt     # TLS certificate (safe to share)
│   └── server.key     # Private key (NEVER commit to GitHub)
└── tests/
    ├── test_dfs.py    # Functional test suite
    ├── benchmark.py   # Performance measurement
    └── stress_test.py # Concurrent load test
```

---

## Setup

### Prerequisites

```
Python 3.11+
pip install Pillow pypdf python-docx
```

For DOCX→PDF conversion (optional, better quality):
```
pip install reportlab
```

### Install all dependencies at once

**Windows (venv):**
```
python -m venv venv --without-pip
.\venv\Scripts\Activate.ps1
python -m ensurepip --upgrade
pip install Pillow pypdf python-docx reportlab
```

**Linux/Mac:**
```
python3 -m venv venv
source venv/bin/activate
pip install Pillow pypdf python-docx reportlab
```

---

## Generating SSL Certificates

### Windows (using Git Bash)

Open Git Bash and run as ONE single line:
```
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=localhost"
```

For multi-device (replace with your actual IP):
```
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=192.168.x.x" -addext "subjectAltName=IP:192.168.x.x,IP:127.0.0.1,DNS:localhost"
```

If Git Bash is not in PATH, add OpenSSL to PATH first (in PowerShell):
```
$env:PATH += ";C:\Program Files\Git\usr\bin"
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=localhost"
```

### Linux / Mac

```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout certs/server.key -out certs/server.crt \
  -days 365 -nodes \
  -subj "/CN=localhost"
```

For multi-device:
```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout certs/server.key -out certs/server.crt \
  -days 365 -nodes \
  -subj "/CN=192.168.x.x" \
  -addext "subjectAltName=IP:192.168.x.x,IP:127.0.0.1,DNS:localhost"
```

Verify certificate:
```
openssl x509 -in certs/server.crt -text -noout
```

---

## Running the Project

### Windows

**Terminal 1 — Start DFS server:**
```
.\venv\Scripts\Activate.ps1
python server.py
```

**Terminal 2 — Start web frontend:**
```
.\venv\Scripts\Activate.ps1
python web_server.py
```
Then open: http://localhost:8080

**Terminal 2 (alternative) — Use CLI client:**
```
.\venv\Scripts\Activate.ps1
python client.py ping
python client.py convert photo.png --to jpg --out results
```

### Linux / Mac

**Terminal 1 — Start DFS server:**
```
source venv/bin/activate
python3 server.py
```

**Terminal 2 — Start web frontend:**
```
source venv/bin/activate
python3 web_server.py
```
Then open: http://localhost:8080

**Terminal 2 (alternative) — Use CLI client:**
```
source venv/bin/activate
python3 client.py ping
python3 client.py convert photo.png --to jpg --out results
```

### Multi-device (different laptops on same WiFi)

Find your IP first:
- Windows: `ipconfig` → look for IPv4 Address under Wi-Fi
- Linux: `ip a` or `hostname -I`

Start server (same as above). Connect from another device:
```
# Windows
python client.py --host <your-ip> ping

# Linux
python3 client.py --host <your-ip> ping
```

The other device needs a copy of your `certs/server.crt` (not the .key file).

---

## Running Tests

Server must be running before running any test.

**Functional tests:**
```
# Windows
python tests/test_dfs.py

# Linux
python3 tests/test_dfs.py
```

**Performance benchmark:**
```
# Windows
python tests/benchmark.py --concurrent 1 4 8 16

# Linux
python3 tests/benchmark.py --concurrent 1 4 8 16
```

**Stress test (concurrent clients):**
```
# Windows
python tests/stress_test.py --clients 8 --size 50

# Linux
python3 tests/stress_test.py --clients 8 --size 50
```

---

## Security Notes

- TLS 1.2+ enforced on all connections
- MD5 checksum verified on every upload and download
- Each client can only access its own jobs
- Never commit `certs/server.key` to GitHub
- Add to `.gitignore`: `certs/server.key`, `venv/`, `__pycache__/`

---

## Rubric Coverage

| Criterion | Implementation |
|-----------|---------------|
| Problem Definition & Architecture | README architecture diagram, clear component separation |
| Core Implementation | Raw sockets: `socket.socket`, `bind`, `listen`, `accept`, `wrap_socket`, manual framing in `protocol.py` |
| Feature Implementation (D1) | Image/text/doc conversion, SSL, multi-client concurrency, job scheduling |
| Performance Evaluation | `tests/benchmark.py` — latency, throughput, concurrency tables |
| Optimisation & Fixes | Priority scheduling, MD5 integrity, graceful disconnect, edge-case handling |
| Final Demo (D2) | Frontend UI, full test suite, CLI, GitHub with complete documentation |
