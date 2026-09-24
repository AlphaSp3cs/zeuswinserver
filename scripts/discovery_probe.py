import json, socket, urllib.request, urllib.error, sys, os

TARGET_IP = "10.0.188.50"
JSON_CANDIDATES = [
    "/",
    "/api/market",
    "/market",
    "/data",
    "/api/v1/market",
    "/api/v1/data",
    "/ohlc",
    "/prices",
    "/chart",
    "/tickers",
    "/api/status",
    "/status",
    "/health",
    "/api/health",
    "/api",
    "/api/v1",
]
PORTS = [8080, 9000, 5000, 5001]
SOURCES_PATH = os.path.expanduser(r"C:/Users/bravo-usr1/.hermes/data/market_collector/sources.json")

results = {"3001": {}, "ports": {}}

def fetch_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"Accept": "application/json, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type","")
            body = resp.read(4096).decode("utf-8", errors="ignore")
            # try parse json
            try:
                data = json.loads(body)
                return {"status": resp.status, "content_type": ct, "json": data, "url": url}
            except Exception:
                return {"status": resp.status, "content_type": ct, "text_preview": body[:500], "url": url}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": str(e), "url": url}
    except Exception as e:
        return {"status": None, "error": str(e), "url": url}

def scan_port(ip, port, timeout=3):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        banner = s.recv(1024).decode("utf-8", errors="ignore") if False else ""
        s.close()
        return {"state": "open", "banner": banner}
    except Exception as e:
        s.close()
        return {"state": "closed/filtered", "error": str(e)}

# probe 3001 endpoints
print("[*] Probing http://%s:3001 JSON endpoints" % TARGET_IP)
for path in JSON_CANDIDATES:
    url = f"http://{TARGET_IP}:3001{path}"
    res = fetch_json(url)
    results["3001"][path] = res
    st = res.get("status")
    if st == 200:
        preview = ""
        if "json" in res:
            preview = str(res["json"])[:120].replace("\n"," ")
        else:
            preview = (res.get("text_preview","") or "")[:120].replace("\n"," ")
        print(f"  200 {path} -> {preview}")
    elif st:
        print(f"  {st} {path}")
    else:
        print(f"  ERR {path} -> {res.get('error','')}")

# scan ports
print("[*] Scanning ports %s on %s" % (PORTS, TARGET_IP))
for p in PORTS:
    res = scan_port(TARGET_IP, p)
    results["ports"][str(p)] = res
    print(f"  {p}: {res['state']}{(' '+res.get('error','')) if res['state']!='open' else ''}")

# append new findings to sources.json if file exists
new_entries = []
# derive new from results where we see something useful
useful_3001 = [path for path, res in results["3001"].items() if res.get("status") == 200 and ("json" in res or "text_preview" in res)]
for path in useful_3001:
    new_entries.append({"url": f"http://{TARGET_IP}:3001{path}", "type": "json", "source": "discovery_probe", "discovered_at": "%s" % __import__('datetime').datetime.now().isoformat()})
for p, res in results["ports"].items():
    if res["state"] == "open":
        # just report open; can't assert http/json without more probes
        new_entries.append({"host": TARGET_IP, "port": int(p), "type": "open_port", "source": "discovery_probe", "discovered_at": "%s" % __import__('datetime').datetime.now().isoformat()})

if new_entries:
    existing = []
    if os.path.exists(SOURCES_PATH):
        try:
            with open(SOURCES_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
        except Exception as e:
            print("[WARN] Could not read existing sources.json: %s" % e)
            existing = []
    combined = existing + new_entries
    try:
        os.makedirs(os.path.dirname(SOURCES_PATH), exist_ok=True)
        with open(SOURCES_PATH, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2)
        print(f"[+] Appended {len(new_entries)} new entry/entries to sources.json")
    except Exception as e:
        print("[ERROR] Writing sources.json: %s" % e)
else:
    print("[-] No new useful findings to append.")

print("\n--- SUMMARY ---")
print(json.dumps(results, indent=2)[:2000])
