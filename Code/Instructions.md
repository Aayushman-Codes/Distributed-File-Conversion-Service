# DFS — Quick Command Reference

## Install Dependencies

```
pip install Pillow pypdf python-docx reportlab
```

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
HH:MM:SS  INFO  Scheduler started with 4 workers
HH:MM:SS  INFO  DFS Server listening on 0.0.0.0:9000  (TLS, 4 workers)
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

Expected output:
```
HH:MM:SS  INFO  DFS Web Server running at http://localhost:8080
HH:MM:SS  INFO  Other devices on the network: http://192.168.x.x:8080
```

The second line shows the URL other devices on the same network should open.
Open your browser at the URL shown in the output.

---

## Using the Browser UI (Any Device)

1. Open the URL shown in the web_server.py output in any browser
2. Drop a file onto the page or click Browse Files
3. Select the target format from the chips that appear
4. Click CONVERT FILE
5. Wait for the progress bar to reach DONE
6. Click the Download button — the file saves with the original filename

The browser UI works from any device on the same network.
No certificate setup needed for browser access.

---

## CLI Client Commands (Terminal 2 alternative)

### Ping
```
# Windows (same machine)
python client.py ping

# Windows (other device)
python client.py --host <server-ip> ping

# Linux
python3 client.py ping
python3 client.py --host <server-ip> ping
```

### Convert a file (one shot — upload + wait + download)
```
# Windows
python client.py convert C:\path\to\file.docx --to pdf --out results
python client.py --host <server-ip> convert C:\path\to\file.docx --to pdf --out results

# Linux
python3 client.py convert /home/user/file.docx --to pdf --out results
python3 client.py --host <server-ip> convert /home/user/file.docx --to pdf --out results
```

### Upload only (get job ID)
```
python client.py upload file.png --to jpg
```

### Check job status
```
python client.py status <job_id>
```

### Download result
```
python client.py download <job_id> --out results
```

### List all jobs
```
python client.py jobs
```

---

## Supported Conversions

### Images
| Input | Available Output Formats |
|-------|--------------------------|
| PNG | jpg, bmp, gif, webp, tiff |
| JPG / JPEG | png, bmp, gif, webp, tiff |
| BMP | png, jpg, gif, webp |
| GIF | png, jpg, bmp |
| WEBP | png, jpg, bmp |
| TIFF | png, jpg, bmp |

### Text / Data
| Input | Available Output Formats |
|-------|--------------------------|
| TXT | csv, json, xml |
| CSV | txt, json, xml |
| JSON | txt, csv, xml |
| XML | txt, csv, json |

### Documents
| Input | Available Output Formats |
|-------|--------------------------|
| PDF | txt, docx |
| DOCX | txt, pdf |

DOCX → PDF preserves headings, body text, tables, and embedded images.

---

## Connect from Another Device (Multi-Device Setup)

### Browser (recommended — no setup needed)
1. Start server.py and web_server.py on the host machine
2. Note the IP printed by web_server.py:
   `Other devices on the network: http://192.168.x.x:8080`
3. Open that URL in any browser on any device on the same network
4. Everything works — no certificate needed for browser access

### CLI from another device
The CLI client connects directly over SSL/TCP and needs the certificate.

**Step 1 — Find the server IP:**
- Windows: `ipconfig` → IPv4 Address under Wi-Fi
- Linux: `ip a` or `hostname -I`

**Step 2 — Regenerate the certificate with the server IP as SAN:**

Windows (Git Bash):
```
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt \
  -days 365 -nodes \
  -subj "/CN=192.168.x.x" \
  -addext "subjectAltName=IP:192.168.x.x,IP:127.0.0.1,DNS:localhost"
```

Linux / Mac:
```
openssl req -x509 -newkey rsa:4096 \
  -keyout certs/server.key -out certs/server.crt \
  -days 365 -nodes \
  -subj "/CN=192.168.x.x" \
  -addext "subjectAltName=IP:192.168.x.x,IP:127.0.0.1,DNS:localhost"
```

**Step 3 — Copy server.crt to the other device:**
Copy only `certs/server.crt` (never the .key file) into the `certs/` folder
on the other device. The other device needs the full project files.

**Step 4 — Connect:**
```
python client.py --host 192.168.x.x ping
python client.py --host 192.168.x.x convert file.png --to jpg --out results
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
python tests/benchmark.py
python tests/benchmark.py --concurrent 1 4 8 16
```

### Stress Test
```
python tests/stress_test.py --clients 8 --size 50
python tests/stress_test.py --clients 16 --size 100
```

---

## Deliverable Verification

### Multiple Clients — Option A (manual)
Open 3 extra terminals, activate venv in each, run convert in all at the same time.
Watch server terminal — you will see simultaneous client connections logged.

### Multiple Clients — Option B (automated, recommended)
```
python tests/stress_test.py --clients 8 --size 50
```

### SSL Proof — Show cipher
```
python client.py ping
```
Output shows: `cipher: ('TLS_AES_256_GCM_SHA384', 'TLSv1.3', 256)`

### SSL Proof — Show certificate
```
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

### Localhost only

Windows (Git Bash):
```
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=localhost"
```

Linux / Mac:
```
openssl req -x509 -newkey rsa:4096 \
  -keyout certs/server.key \
  -out certs/server.crt \
  -days 365 -nodes \
  -subj "/CN=localhost"
```

### Multi-device (replace 192.168.x.x with your actual IP)

Windows (Git Bash):
```
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=192.168.x.x" -addext "subjectAltName=IP:192.168.x.x,IP:127.0.0.1,DNS:localhost"
```

Linux / Mac:
```
openssl req -x509 -newkey rsa:4096 \
  -keyout certs/server.key -out certs/server.crt \
  -days 365 -nodes \
  -subj "/CN=192.168.x.x" \
  -addext "subjectAltName=IP:192.168.x.x,IP:127.0.0.1,DNS:localhost"
```

If openssl is not found on Windows, add it to PATH first:
```
$env:PATH += ";C:\Program Files\Git\usr\bin"
```

Verify certificates were created:
```
ls certs/
```
Must show both: `server.crt` and `server.key`

---

## Notes

- Always activate venv before every terminal session
- Always start server.py before web_server.py or any client command
- Converted files go into the `results/` folder (CLI) or browser download (UI)
- Server terminal shows every connection and job — keep it visible during demo
- server.key must NEVER be committed to GitHub
- Job history in the browser is per-session — clearing cookies resets it
- Storage folder is created automatically in the system temp directory
