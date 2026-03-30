# DFS — Quick Command Reference

pip install Pillow pypdf python-docx reportlab
---

## Every Terminal — Always Do This First

**Windows:**
```
.\venv\Scripts\Activate.ps1
```

**Linux / Mac:**
```
source venv/bin/activate
```

---

## Start the Backend Server (Terminal 1)

**Windows:**
```
python server.py
```

**Linux / Mac:**
```
python3 server.py
```

Expected output:
```
HH:MM:SS  INFO  MainThread  Scheduler started with 4 workers
HH:MM:SS  INFO  MainThread  DFS Server listening on 0.0.0.0:9000  (TLS, 4 workers)
```
Leave this terminal open.

---

## Start the Web Frontend (Terminal 2)

**Windows:**
```
python web_server.py
```

**Linux / Mac:**
```
python3 web_server.py
```

Then open your browser at: **http://localhost:8080**

---

## CLI Client Commands (Terminal 2 alternative)

### Ping
```
# Windows
python client.py ping

# Linux
python3 client.py ping
```

### Convert a file (one shot — upload + wait + download)
```
# Windows
python client.py convert C:\path\to\file.png --to jpg --out results

# Linux
python3 client.py convert /home/user/file.png --to jpg --out results
```

### Upload only (get job ID)
```
python client.py upload file.png --to jpg
python3 client.py upload file.png --to jpg
```

### Check job status
```
python client.py status <job_id>
python3 client.py status <job_id>
```

### Download result
```
python client.py download <job_id> --out results
python3 client.py download <job_id> --out results
```

### List all jobs
```
python client.py jobs
python3 client.py jobs
```

---

## Image Conversions

| Command | What it does |
|---------|--------------|
| `--to jpg` | Convert to JPEG (lossy, smaller file) |
| `--to png` | Convert to PNG (lossless) |
| `--to bmp` | Convert to BMP (lossless, large file) |
| `--to webp` | Convert to WebP (modern, efficient) |
| `--to gif` | Convert to GIF |
| `--to tiff` | Convert to TIFF |

---

## Text / Data Conversions

| Command | What it does |
|---------|--------------|
| `--to csv` | Convert to CSV |
| `--to json` | Convert to JSON |
| `--to txt` | Convert to plain text |
| `--to xml` | Convert to XML |

---

## Document Conversions

| Command | What it does |
|---------|--------------|
| `pdf --to txt` | Extract text from PDF |
| `pdf --to docx` | Convert PDF to Word document |
| `docx --to txt` | Extract text from Word document |
| `docx --to pdf` | Convert Word document to PDF |

---

## Connect from Another Device (Multi-System)

First find the server machine's IP:
- **Windows:** `ipconfig` → IPv4 Address under Wi-Fi
- **Linux:** `ip a` or `hostname -I`

On the other device (must have project files + server.crt in certs/):
```
# Windows
python client.py --host <server-ip> ping
python client.py --host <server-ip> convert file.png --to jpg --out results

# Linux
python3 client.py --host <server-ip> ping
python3 client.py --host <server-ip> convert file.png --to jpg --out results
```

---

## Tests

Server must be running before any test.

### Functional Tests
```
# Windows
python tests/test_dfs.py

# Linux
python3 tests/test_dfs.py
```
Expected: `Ran 14 tests ... OK`

### Performance Benchmark
```
# Windows
python tests/benchmark.py
python tests/benchmark.py --concurrent 1 4 8 16

# Linux
python3 tests/benchmark.py
python3 tests/benchmark.py --concurrent 1 4 8 16
```

### Stress Test
```
# Windows
python tests/stress_test.py --clients 8 --size 50
python tests/stress_test.py --clients 16 --size 100

# Linux
python3 tests/stress_test.py --clients 8 --size 50
python3 tests/stress_test.py --clients 16 --size 100
```

---

## Deliverable 1 Verification

### Multiple Clients — Option A (manual)
Open 3 extra terminals, activate venv in each, run convert in all at same time.
Watch server terminal — you will see 3 simultaneous client connections logged.

### Multiple Clients — Option B (automated, recommended)
```
python tests/stress_test.py --clients 8 --size 50
python3 tests/stress_test.py --clients 8 --size 50
```

### SSL Proof — Show cipher
```
python client.py ping
```
Output shows: `cipher: ('TLS_AES_256_GCM_SHA384', 'TLSv1.3', 256)`

### SSL Proof — Show certificate
```
# Windows Git Bash or Linux terminal
openssl x509 -in certs/server.crt -text -noout
```

### SSL Proof — Prove client refuses without cert
```
# Git Bash / Linux
mv certs/server.crt certs/server.crt.bak
python client.py ping         # will fail with cert error
mv certs/server.crt.bak certs/server.crt
```

---

## Generating SSL Certificates

### Windows (run in Git Bash as one single line)
```
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=localhost"
```

If openssl is not found, add it to PATH first (in PowerShell):
```
$env:PATH += ";C:\Program Files\Git\usr\bin"
```
Then run the openssl command above.

### Linux / Mac
```
openssl req -x509 -newkey rsa:4096 \
  -keyout certs/server.key \
  -out certs/server.crt \
  -days 365 -nodes \
  -subj "/CN=localhost"
```

### Verify certificates were created
```
ls certs/
```
Must show both: `server.crt` and `server.key`

---

## Notes

- Always activate venv before every terminal session
- Always start server.py before any client command or web_server.py
- Converted files go into the `results/` folder
- Server terminal shows every connection and job — keep it visible during demo
- server.key must NEVER be committed to GitHub
