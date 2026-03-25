import requests
import schedule
import time
import json
import os
from datetime import datetime, timedelta

API_KEY    = "c6ad0124-e930-432d-9af2-c7983987232a"
API_SECRET = "5LRr5baG5gzdF9pW7LDDFusswDYKyxF1"
TELEGRAM_BOT_TOKEN = "263996056:AAE-Ys6lh3HdhX8Xc8MJ2W5AgD0hYITzJFo"
TELEGRAM_CHAT_ID   = "267436315"
API_BASE               = "https://pool-api.sbicrypto.com"
STATE_FILE             = "/tmp/worker_state.json"
CHECK_INTERVAL_MINUTES = 10

HEADERS = {
    "X-API-Key":    API_KEY,
    "X-API-Secret": API_SECRET,
    "Accept":       "application/json",
}

def get_worker_counts():
    try:
        r = requests.get(f"{API_BASE}/api/external/v1/workers",
            headers=HEADERS, params={"subaccountNames": "Aerg_BTC"}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            workers = data.get("content", data.get("data", data))
            if isinstance(workers, list):
                online   = sum(1 for w in workers if str(w.get("status","")).upper() == "ONLINE")
                offline  = sum(1 for w in workers if str(w.get("status","")).upper() == "OFFLINE")
                inactive = sum(1 for w in workers if str(w.get("status","")).upper() == "DEAD")
                return online, offline, inactive, len(workers)
    except Exception as e:
        print(f"  [workers Aerg_BTC] error: {e}")
    try:
        r = requests.get(f"{API_BASE}/api/external/v1/workers",
            headers=HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json()
            workers = data.get("content", data.get("data", data))
            if isinstance(workers, list):
                online   = sum(1 for w in workers if str(w.get("status","")).upper() == "ONLINE")
                offline  = sum(1 for w in workers if str(w.get("status","")).upper() == "OFFLINE")
                inactive = sum(1 for w in workers if str(w.get("status","")).upper() == "DEAD")
                return online, offline, inactive, len(workers)
    except Exception as e:
        print(f"  [workers all] error: {e}")
    try:
        r = requests.get(f"{API_BASE}/api/external/v1/subaccounts",
            headers=HEADERS, params={"subaccountNames": "Aerg_BTC"}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data.get("content", data.get("data", data))
            if isinstance(items, list) and items:
                acc = items[0]
                online   = int(acc.get("onlineWorkers",   acc.get("activeWorkerCount",   0)))
                offline  = int(acc.get("offlineWorkers",  acc.get("inactiveWorkerCount", 0)))
                inactive = int(acc.get("inactiveWorkers", 0))
                total    = int(acc.get("totalWorkers",    acc.get("workerCount", online + offline)))
                return online, offline, inactive, total
    except Exception as e:
        print(f"  [subaccounts] error: {e}")
    raise RuntimeError("Failed to get worker data from any endpoint")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=15)
    except Exception as e:
        print(f"  Telegram error: {e}")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"history": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_value_24h_ago(history):
    threshold = datetime.utcnow() - timedelta(hours=24)
    candidates = [e for e in history if datetime.fromisoformat(e["ts"]) <= threshold]
    return candidates[-1]["online"] if candidates else None

def check():
    now_str = datetime.utcnow().isoformat()
    now_fmt = datetime.utcnow().strftime("%Y-%m-%d %H:%M") + " UTC"
    print(f"[{now_fmt}] Checking workers...", flush=True)
    try:
        online, offline, inactive, total = get_worker_counts()
    except Exception as e:
        msg = f"\u26a0\ufe0f <b>BTC Mining Monitor - Error!</b>\n\U0001f550 {now_fmt}\n<code>{e}</code>"
        send_telegram(msg)
        print(f"  ERROR: {e}", flush=True)
        return
    state = load_state()
    history = state["history"]
    online_24h = get_value_24h_ago(history)
    history.append({"ts": now_str, "online": online, "offline": offline, "inactive": inactive})
    state["history"] = history[-300:]
    save_state(state)
    print(f"  Online: {online}  Offline: {offline}  Dead: {inactive}  | 24h ago: {online_24h}", flush=True)
    if online_24h is not None and online != online_24h:
        diff  = online - online_24h
        arrow = "\U0001f4c8" if diff > 0 else "\U0001f4c9"
        msg = (
            f"{arrow} <b>BTC Mining - Worker Change!</b>\n\n"
            f"\U0001f550 {now_fmt}\n"
            f"\U0001f7e2 Online now:  <b>{online}</b>\n"
            f"\U0001f534 Offline now: <b>{offline}</b>\n"
            f"\u26ab Dead/Inactive: <b>{inactive}</b>\n\n"
            f"\U0001f4c5 Online 24h ago: <b>{online_24h}</b>\n"
            f"\U0001f4ca Change: <b>{diff:+d} workers</b>\n\n"
            f"\U0001f517 <a href='https://pool.sbicrypto.com/dashboard'>Open Dashboard</a>"
        )
        send_telegram(msg)
        print(f"  Notification sent (change: {diff:+d})", flush=True)
    else:
        print("  No change.", flush=True)

if __name__ == "__main__":
    print("BTC Mining Monitor started", flush=True)
    send_telegram(
        "\U0001f680 <b>BTC Mining Monitor started</b>\n\n"
        f"\u26cf Subaccount: Aerg_BTC\n"
        f"\U0001f501 Check every {CHECK_INTERVAL_MINUTES} min\n"
        f"\U0001f514 Alert on worker count change vs 24h ago\n\n"
        f"\U0001f517 <a href='https://pool.sbicrypto.com/dashboard'>Dashboard</a>"
    )
    check()
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check)
    while True:
        schedule.run_pending()
        time.sleep(30)
