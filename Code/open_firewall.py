"""
open_firewall.py — Opens ports 8080 (web UI) and 9000 (DFS TCP) in the
Windows Firewall so other devices on the network can connect.

Run once as Administrator:
    python open_firewall.py

On Linux/Mac use ufw or iptables instead (see printed instructions).
"""

import sys
import subprocess
import platform

WEB_PORT = 8080
DFS_PORT = 9000

RULES = [
    ("DFS-Web-8080",  WEB_PORT,  "Web frontend — browser access from other devices"),
    ("DFS-TCP-9000",  DFS_PORT,  "DFS TCP server — CLI client access from other devices"),
]

def add_windows_rule(name, port, description):
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={name}",
        "protocol=TCP",
        "dir=in",
        f"localport={port}",
        "action=allow",
        f"description={description}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  [OK]  Port {port} opened  ({name})")
    else:
        # Rule may already exist — try updating it
        cmd[4] = "set"
        result2 = subprocess.run(cmd, capture_output=True, text=True)
        if result2.returncode == 0:
            print(f"  [OK]  Port {port} rule updated  ({name})")
        else:
            print(f"  [!!]  Port {port} failed: {result.stdout.strip() or result.stderr.strip()}")
            print(f"        Run PowerShell as Administrator and try manually:")
            print(f"        netsh advfirewall firewall add rule name=\"{name}\" "
                  f"protocol=TCP dir=in localport={port} action=allow")

def main():
    if platform.system() != "Windows":
        print("Linux/Mac — run these commands instead:")
        for _, port, _ in RULES:
            print(f"  sudo ufw allow {port}/tcp")
        print("  sudo ufw reload")
        return

    print("Opening firewall ports for DFS...")
    print()
    for name, port, desc in RULES:
        add_windows_rule(name, port, desc)
    print()
    print("Done. Other devices on the same WiFi can now reach:")

    import socket
    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        lan_ip = "<your-ip>"

    print(f"  Browser UI:  http://{lan_ip}:{WEB_PORT}")
    print(f"  CLI client:  python client.py --host {lan_ip} ping")
    print()
    print("Note: If you still get connection errors, check that both")
    print("  server.py and web_server.py are running on this machine.")

if __name__ == "__main__":
    main()
