# Distributed File Conversion Service (DFS)

A secure, multi-client distributed file conversion service built with **raw TCP sockets + SSL/TLS** in Python. Designed for the Jackfruit Mini Project (Socket Programming).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT SIDE                          │
│                                                             │
│   client.py (CLI)  ──►  client_lib.py (DFSClient)          │
│   tests/stress_test.py                                      │
│   tests/benchmark.py                                        │
└────────────────────────┬────────────────────────────────────┘
                         │  TCP + SSL/TLS (port 9000)
                         │  Framed binary protocol
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        SERVER SIDE                          │
│                                                             │
│   server.py                                                 │
│   ├── Accept loop (main thread)                             │
│   ├── ClientHandler threads (1 per connection)              │
│   ├── JobScheduler (priority queue + worker pool)           │
│   │   └── converter.py (Pillow / stdlib)                    │
│   └── SSL Context (TLS 1.2+)                                │
└─────────────────────────────────────────────────────────────┘
```

### Key design decisions

| Concern | Decision |
|---|---|
| **Transport** | Raw TCP sockets, no HTTP/framework |
| **Security** | TLS 1.2+ with self-signed cert; MD5 integrity on every transfer |
| **Concurrency** | 1 thread per client; configurable converter worker pool |
| **Scheduling** | Priority queue — smaller files run first to minimise wait time |
| **Protocol** | Custom binary framing: `[4B header-len][JSON header][4B payload-len][bytes]` |

---

## Wire Protocol

Every message — in both directions — is encoded as:

```
 ┌───────────────┬──────────────────┬────────────────┬──────────────────┐
 │  4 B (uint32) │   N bytes UTF-8  │  4 B (uint32)  │   M bytes raw    │
 │  header length│   JSON header    │ payload length │   binary payload │
 └───────────────┴──────────────────┴────────────────┴──────────────────┘
```

### Message types

| Type | Direction | Purpose |
|---|---|---|
| `UPLOAD_REQUEST` | C→S | Declare intent to upload (format, filename, size, MD5) |
| `JOB_ACCEPTED` | S→C | Server ready for binary data |
| `UPLOAD_DATA` | C→S | Raw file bytes as payload |
| `JOB_STATUS` | both | Poll job state / server push after upload |
| `DOWNLOAD_REQUEST` | C→S | Fetch converted file |
| `DOWNLOAD_DATA` | S→C | Converted file bytes + MD5 |
| `LIST_JOBS` | C→S | List all jobs for this client |
| `JOB_LIST` | S→C | Job list response |
| `PING` / `PONG` | both | Latency check |
| `ERROR` | both | Error details |

---

## Supported Conversions

| Input | Output formats |
|---|---|
| PNG | JPG, BMP, GIF, WEBP, TIFF |
| JPG/JPEG | PNG, BMP, GIF, WEBP, TIFF |
| BMP | PNG, JPG, GIF, WEBP |
| WEBP | PNG, JPG, BMP |
| GIF | PNG, JPG, BMP |
| TIFF | PNG, JPG, BMP |
| JSON | CSV, TXT |
| CSV | JSON, TXT |
| TXT | CSV, JSON |

---

## Project Structure

```
dfs/
├── protocol.py        # Shared constants, framing, send/recv helpers
├── server.py          # SSL server + ClientHandler threads
├── scheduler.py       # Priority job queue + worker thread pool
├── converter.py       # Pillow image + stdlib text conversion
├── client_lib.py      # Reusable Python client library (DFSClient)
├── client.py          # Interactive CLI client
├── certs/
│   ├── server.crt     # Self-signed TLS certificate
│   └── server.key     # Private key
└── tests/
    ├── test_dfs.py    # Functional test suite (unittest)
    ├── benchmark.py   # Performance measurement
    └── stress_test.py # Concurrent client load test
```

---

## Setup

### Prerequisites

```bash
Python 3.11+
pip install Pillow
openssl   # for cert generation (usually pre-installed)
```

### 1 — Generate TLS certificates (already done if cloning this repo)

```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout certs/server.key -out certs/server.crt \
  -days 365 -nodes \
  -subj "/C=IN/ST=TN/L=Chennai/O=DFS/CN=localhost"
```

### 2 — Start the server

```bash
python server.py
# or with options:
python server.py --host 0.0.0.0 --port 9000 --workers 8
```

### 3 — Use the CLI client

```bash
# One-shot convert (upload + wait + download)
python client.py convert photo.png --to jpg --out ./results

# Step by step
python client.py upload photo.png --to jpg
# → Job submitted: <job_id>

python client.py status <job_id>
python client.py download <job_id> --out ./results

# List all your jobs
python client.py jobs

# Check latency
python client.py ping
```

---

## Running Tests

```bash
# Functional tests (server must be running)
python tests/test_dfs.py

# Performance benchmark
python tests/benchmark.py --concurrent 1 2 4 8

# Stress test (16 simultaneous clients)
python tests/stress_test.py --clients 16 --size 100
```

---

## Performance Results (sample)

### File-size scalability (PNG → JPEG, single client)

| Size | Upload(s) | Convert(s) | Download(s) | Total(s) | Throughput |
|------|-----------|------------|-------------|----------|------------|
| 1 KB | 0.002 | 0.015 | 0.001 | 0.018 | 55 KB/s |
| 100 KB | 0.004 | 0.020 | 0.003 | 0.027 | 3700 KB/s |
| 1 MB | 0.018 | 0.045 | 0.012 | 0.075 | 13333 KB/s |
| 2 MB | 0.035 | 0.080 | 0.022 | 0.137 | 14598 KB/s |

### Concurrency (100 KB PNG → JPEG)

| Clients | Avg Total(s) | Min(s) | Max(s) |
|---------|-------------|--------|--------|
| 1 | 0.027 | 0.027 | 0.027 |
| 4 | 0.038 | 0.030 | 0.062 |
| 8 | 0.065 | 0.041 | 0.105 |
| 16 | 0.123 | 0.055 | 0.204 |

---

## Security

- **TLS 1.2+ enforced** on all client/server communication
- **MD5 checksum** verified on every upload and download
- **Client isolation**: each client can only view/download its own jobs
- Certificate verification via `ssl.PROTOCOL_TLS_CLIENT` on the client side

---

## Evaluation Coverage (Rubric Mapping)

| Criterion | How it's addressed |
|---|---|
| Problem Definition & Architecture | This README + architecture diagram; clear component separation |
| Core Implementation | Raw sockets: `socket.socket`, `bind`, `listen`, `accept`, `wrap_socket`; manual framing in `protocol.py` |
| Feature Implementation (D1) | Image + text conversion, SSL, multi-client concurrency, job scheduling |
| Performance Evaluation | `tests/benchmark.py` — latency, throughput, concurrency analysis |
| Optimisation & Fixes | Priority scheduling, MD5 integrity, graceful disconnect handling, edge-case tests |
| Final Demo (D2) | `tests/test_dfs.py` full suite; CLI demo via `client.py convert` |
