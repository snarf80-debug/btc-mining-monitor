import requests
import schedule
import time
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

API_KEY               = "c6ad0124-e930-432d-9af2-c7983987232a"
API_SECRET            = "5LRr5baG5gzdF9pW7LDDFusswDYKyxF1"
TELEGRAM_BOT_TOKEN   = "263996056:AAE-Ys6lh3HdhX8Xc8MJ2W5AgD0hYITzJFo"
TELEGRAM_CHAT_ID     = "267436315"
API_BASE              = "https://pool-api.sbicrypto.com"
STATE_FILE            = "/tmp/worker_state.json"
CHECK_INTERVAL_MINUTES = 10

HEADERS = {
    "X-API-Key":    API_KEY,
    "X-API-Secret": API_SECRET,
    "Accept":       "application/json",
}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BTC Mining Monitor OK")
    def log_message(self, format, *args):
        pass


def start_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"HTTP server listening on port {port}", flush=True)
    server.serve_forever()


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"Telegram response: {r.status_code} {r.text}", flush=True)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)


def get_all_workers():
    workers = []
    page = 1
    while True:
        try:
            r = requests.get(
                f"{API_BASE}/api/external/v1/workers",
                headers=HEADERS,
                params={"page": page, "size": 100},
                timeout=30,
            )
            print(f"API page {page}: status={r.status_code}", flush=True)
            if r.status_code != 200:
                print(f"API error body: {r.text[:500]}", flush=True)
                break
            data = r.json()
            print(f"API page {page} keys: {list(data.keys()) if isinstance(data, dict) else type(data)}", flush=True)
            # handle different response shapes
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("data") or data.get("workers") or data.get("items") or data.get("list") or []
                if not isinstance(items, list):
                    # maybe the dict itself is one worker
                    items = [data]
            else:
                items = []
            print(f"API page {page}: {len(items)} items", flush=True)
            workers.extend(items)
            # pagination
            total = None
            if isinstance(data, dict):
                total = data.get("total") or data.get("totalCount") or data.get("count")
            if total is None or len(workers) >= total or len(items) < 100:
                break
            page += 1
        except Exception as e:
            print(f"Worker fetch error: {e}", flush=True)
            break
    return workers


def count_online(workers):
    online = 0
    for w in workers:
        status = str(w.get("status", "") or w.get("workerStatus", "") or "").lower()
        if status in ("online", "active", "1", "true"):
            online += 1
    return online


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def check():
    now = datetime.now(timezone.utc)
    now_fmt = now.strftime("%Y-%m-%d %H:%M") + " UTC"
    print(f"[{now_fmt}] Checking workers...", flush=True)

    workers = get_all_workers()
    total = len(workers)
    online = count_online(workers)
    print(f"Total workers: {total}  Online: {online}", flush=True)

    # Send raw sample for debug
    sample = json.dumps(workers[:2], ensure_ascii=False)[:400] if workers else "[]"
    print(f"Sample: {sample}", flush=True)

    state = load_state()
    threshold = now - timedelta(hours=24)

    # find online count 24h ago
    history = state.get("history", [])
    online_24h = None
    for entry in reversed(history):
        if datetime.fromisoformat(entry["ts"]) <= threshold:
            online_24h = entry["online"]
            break

    # append current
    history.append({"ts": now.isoformat(), "online": online})
    # keep only last 48h
    cutoff = (now - timedelta(hours=48)).isoformat()
    history = [e for e in history if e["ts"] >= cutoff]
    state["history"] = history
    save_state(state)

    print(f"Online: {online}  Online 24h ago: {online_24h}", flush=True)

    if online_24h is None:
        msg = (
            f"\U0001f680 <b>BTC Mining Monitor</b>\n\n"
            f"\U0001f4ca First check completed\n"
            f"\U0001f4c5 Time: <b>{now_fmt}</b>\n"
            f"\U0001f4bb Total workers: <b>{total}</b>\n"
            f"\U0001f7e2 Online now: <b>{online}</b>\n"
            f"\u26a0\ufe0f No 24h baseline yet, will alert on next change.\n\n"
            f"\U0001f517 <a href='https://pool.sbicrypto.com/dashboard'>Dashboard</a>"
        )
        send_telegram(msg)
        return

    diff = online - online_24h
    if diff != 0:
        direction = "\U0001f4c8 increased" if diff > 0 else "\U0001f4c9 decreased"
        msg = (
            f"\u26a0\ufe0f <b>Worker count changed!</b>\n\n"
            f"\U0001f4c5 Time: <b>{now_fmt}</b>\n"
            f"\U0001f7e2 Online now: <b>{online}</b>\n"
            f"\U0001f4c6 Online 24h ago: <b>{online_24h}</b>\n"
            f"\U0001f4ca {direction} by <b>{abs(diff)}</b> workers\n\n"
            f"\U0001f517 <a href='https://pool.sbicrypto.com/dashboard'>Dashboard</a>"
        )
        send_telegram(msg)
        print(f"Notification sent (change: {diff:+d})", flush=True)
    else:
        print(" No change.", flush=True)


if __name__ == "__main__":
    print("BTC Mining Monitor v3 started", flush=True)
    t = threading.Thread(target=start_http_server, daemon=True)
    t.start()
    time.sleep(2)
    send_telegram(
        "\U0001f680 <b>BTC Mining Monitor v3 started</b>\n\n"
        "\u26cf Subaccount: Aerg_BTC\n"
        f"\U0001f501 Check every {CHECK_INTERVAL_MINUTES} min\n"
        "\U0001f514 Alert on worker count change vs 24h ago\n\n"
        "\U0001f517 <a href='https://pool.sbicrypto.com/dashboard'>Dashboard</a>"
    )
    check()
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check)
    while True:
        schedule.run_pending()
        time.sleep(30)
