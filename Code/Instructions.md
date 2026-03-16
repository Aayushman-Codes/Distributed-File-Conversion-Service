# Distributed File Conversion Service (DFS)
### Socket Programming Mini Project — Quick Command Reference

---

## Project Setup (One Time Only)

### Activate virtual environment
> Run this in EVERY terminal before using the project
```
.\venv\Scripts\Activate.ps1
```

### Start the server
> Keep this terminal open and running at all times
```
python server.py
```
Expected output:
```
HH:MM:SS  INFO  MainThread  Scheduler started with 4 workers
HH:MM:SS  INFO  MainThread  DFS Server listening on localhost:9000  (TLS, 4 workers)
```

---

## Client Commands
> Open a second terminal, activate venv, then use these commands

### Check server is alive
```
python client.py ping
```
Expected output:
```
INFO  Connected to localhost:9000  (cipher: ('TLS_AES_256_GCM_SHA384', 'TLSv1.3', 256))
PONG from localhost:9000  RTT=x.xx ms
```

### Convert a file (upload + wait + download in one shot)
```
python client.py convert <path-to-file> --to <format> --out results
```

### Upload a file (get a job ID)
```
python client.py upload <path-to-file> --to <format>
```

### Check job status
```
python client.py status <job_id>
```

### Download converted file
```
python client.py download <job_id> --out results
```

### List all your jobs
```
python client.py jobs
```

---

## Image Conversions

### PNG to JPG
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\logo.png --to jpg --out results
```

### PNG to BMP (lossless, no quality loss)
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\logo.png --to bmp --out results
```

### PNG to WEBP
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\logo.png --to webp --out results
```

### PNG to GIF
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\logo.png --to gif --out results
```

### PNG to TIFF
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\logo.png --to tiff --out results
```

### JPG to PNG
```
python client.py convert <path-to-file.jpg> --to png --out results
```

---

## Text Conversions

### JSON to CSV
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\test.json --to csv --out results
```

### JSON to TXT
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\test.json --to txt --out results
```

### CSV to JSON
```
python client.py convert results\test.csv --to json --out results
```

### CSV to TXT
```
python client.py convert results\test.csv --to txt --out results
```

### TXT to JSON
```
python client.py convert results\test.txt --to json --out results
```

### TXT to CSV
```
python client.py convert results\test.txt --to csv --out results
```

---

## Supported Formats

| Input | Supported Output Formats |
|-------|--------------------------|
| PNG | jpg, bmp, gif, webp, tiff |
| JPG / JPEG | png, bmp, gif, webp, tiff |
| BMP | png, jpg, gif, webp |
| GIF | png, jpg, bmp |
| WEBP | png, jpg, bmp |
| TIFF | png, jpg, bmp |
| JSON | csv, txt |
| CSV | json, txt |
| TXT | csv, json |

---

## Running the Tests
> Make sure the server is running in another terminal before running any test

### 1. Functional Test Suite
Tests all conversions, error handling, and job workflow automatically
```
python tests/test_dfs.py
```
Expected output:
```
Ran 14 tests in ~8s
OK
```

### 2. Performance Benchmark
Measures latency, throughput, and scalability
```
python tests/benchmark.py
```
Custom concurrent client counts:
```
python tests/benchmark.py --concurrent 1 4 8 16
```

### 3. Stress Test (Concurrent Clients)
Fires N clients simultaneously and reports results
```
python tests/stress_test.py --clients 8 --size 50
```
For heavier load:
```
python tests/stress_test.py --clients 16 --size 100
```
Expected output:
```
Results: 8/8 succeeded, 0 failed
  avg=0.XXs  min=0.XXs  max=0.XXs
```

---

## Deliverable 1 Verification

### Requirement 1 — Multiple clients with one server

**Option A: Manual demo**
1. Keep server running in terminal 1
2. Open 3 more terminals and activate venv in each
3. Run this in all 3 at the same time:
```
python client.py convert C:\Users\aayus\Desktop\CN_Jackfruit\file_test\logo.png --to jpg --out results
```
4. Watch the server terminal — you will see all 3 clients connected simultaneously:
```
INFO  client-XXXX1  Client connected: 127.0.0.1:XXXX1
INFO  client-XXXX2  Client connected: 127.0.0.1:XXXX2
INFO  client-XXXX3  Client connected: 127.0.0.1:XXXX3
```

**Option B: Automated stress test (recommended)**
```
python tests/stress_test.py --clients 8 --size 50
```
Shows 8 clients all working simultaneously with a clean results summary.

---

### Requirement 2 — SSL Implementation

**Show the cipher on every connection:**
```
python client.py ping
```
Point out this line in the output:
```
cipher: ('TLS_AES_256_GCM_SHA384', 'TLSv1.3', 256)
```
This proves TLS 1.3 with 256-bit encryption is active on every connection.

**Show the certificate details:**
> Run this in Git Bash
```
openssl x509 -in certs/server.crt -text -noout
```
Shows the full certificate — issuer, validity period, RSA 4096-bit key.

**Prove the client won't connect without the certificate:**
> Run in Git Bash to temporarily hide the cert
```
cd certs
mv server.crt server.crt.bak
```
Then in VS Code terminal:
```
python client.py ping
```
You will get a certificate error — proving SSL verification is enforced. Restore the cert after:
```
cd certs
mv server.crt.bak server.crt
```

---

## Notes

- Always start the server before running any client command
- Always activate the venv (`.\venv\Scripts\Activate.ps1`) in every terminal
- Converted files are saved in the `results\` folder
- The server logs every connection and job in its terminal — keep it visible during demo
