# SSL Certificate Generation Guide

---

## Prerequisites

Git for Windows must be installed — it includes OpenSSL.
Download from: https://git-scm.com/download/win

Verify OpenSSL is available by opening Git Bash and running:
```
openssl version
```
Expected output:
```
OpenSSL 3.x.x ...
```

---

## Step 1 — Open Git Bash

Press **Win + S**, search for **Git Bash**, and open it.

---

## Step 2 — Navigate to the certs folder

```
cd /c/Users/aayus/Desktop/CN_Jackfruit/certs
```

Confirm you are in the right place:
```
pwd
```
Expected output:
```
/c/Users/aayus/Desktop/CN_Jackfruit/certs
```

---

## Step 3 — Generate the certificate and private key

```
openssl req -x509 -newkey rsa:4096 \
  -keyout server.key \
  -out server.crt \
  -days 365 \
  -nodes \
  -subj "//CN=localhost"
```

### What each flag means

| Flag | Meaning |
|------|---------|
| `-x509` | Generate a self-signed certificate |
| `-newkey rsa:4096` | Create a new 4096-bit RSA private key |
| `-keyout server.key` | Save the private key to server.key |
| `-out server.crt` | Save the certificate to server.crt |
| `-days 365` | Certificate is valid for 1 year |
| `-nodes` | No password on the private key (so server starts without prompting) |
| `-subj "//CN=localhost"` | Certificate is issued for localhost |

### What you will see

A stream of `+` and `.` characters for about 5–10 seconds while the RSA key is generated, followed by:
```
-----
```
This means it worked successfully.

---

## Step 4 — Verify the files were created

```
ls
```
Expected output:
```
server.crt  server.key
```

---

## Step 5 — Inspect the certificate (optional but good for demo)

```
openssl x509 -in server.crt -text -noout
```

This prints the full certificate details. Key things to point out to an evaluator:

```
Issuer: CN=localhost
Validity
    Not Before: <today's date>
    Not After:  <date one year from now>
Public Key Algorithm: rsaEncryption
    Public-Key: (4096 bit)
```

---

## Certificate Renewal

Certificates expire after 365 days. To renew, simply delete the old files and run Step 3 again:

```
rm server.crt server.key
```

Then rerun the generation command from Step 3.

---

## Proving SSL is enforced (for Deliverable 1 demo)

### Hide the certificate temporarily
```
mv server.crt server.crt.bak
```

### Try to connect — it will fail
In VS Code terminal:
```
python client.py ping
```
You will see a certificate error — proving the client refuses to connect without a valid cert.

### Restore the certificate
```
mv server.crt.bak server.crt
```

---

## File Descriptions

| File | Description |
|------|-------------|
| `server.crt` | Public certificate — shared with clients for verification |
| `server.key` | Private key — never share or commit to GitHub |

---

## Important — Add server.key to .gitignore

Before pushing to GitHub, make sure your `.gitignore` file contains:
```
certs/server.key
```

`server.crt` is safe to commit. `server.key` must never be made public.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `openssl: command not found` | Git for Windows not installed or not in PATH. Reinstall Git. |
| `No such file or directory: certs` | Run `mkdir certs` first, then navigate into it |
| `CERTIFICATE_VERIFY_FAILED` when running client | server.crt is missing from certs folder. Regenerate. |
| `certificate has expired` | Certificate is older than 365 days. Delete both files and regenerate. |
| Permission denied on server.key | Run Git Bash as Administrator |
