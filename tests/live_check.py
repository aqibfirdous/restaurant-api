import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness.reset_db import reset_db

port = 5917
db = os.path.join(tempfile.gettempdir(), "live_rest.db")

def wait_up(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            return True
        except OSError:
            time.sleep(0.3)
    return False

def req(method, path, body=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r) as resp:
        return resp.status, json.loads(resp.read().decode()) if resp.status != 204 else None

reset_db(db, os.path.join(ROOT, "schema.sql"), os.path.join(ROOT, "seed.sql"))
env = dict(os.environ, RESTAURANT_DB=db, PORT=str(port))
errfile = os.path.join(tempfile.gettempdir(), "live_rest_server.log")
proc = subprocess.Popen(
    [sys.executable, "app.py"],
    cwd=os.path.join(ROOT, "src"),
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=open(errfile, "wb"),
)
try:
    assert wait_up(port), "server did not start"
    menu = req("GET", "/menu")
    alice = req("POST", "/customers", {"name": "Alice", "email": "alice@live.example", "phone": "555"})
    tables = req("GET", "/tables")
    table = next(t for t in tables[1] if t["seats"] >= 4)
    res = req("POST", "/reservations", {"customer_id": alice[1]["id"], "dining_table_id": table["id"], "reservation_time": "2026-12-20T19:00:00Z", "party_size": 2})
    items = [i for c in menu[1] for i in c["items"]][:2]
    order = req("POST", "/orders", {"customer_id": alice[1]["id"], "reservation_id": res[1]["id"], "items": [{"menu_item_id": i["id"], "quantity": 1} for i in items]})
    fetched = req("GET", "/orders/%d" % order[1]["id"])
    for st in ("PREPARING", "READY", "COMPLETED"):
        upd = req("PATCH", "/orders/%d/status" % order[1]["id"], {"status": st})
    hist = req("GET", "/customers/%d/orders" % alice[1]["id"])

    assert menu[0] == 200 and alice[0] == 201 and res[0] == 201 and order[0] == 201
    assert fetched[1]["total_cents"] == sum(i["price_cents"] for i in items)
    assert upd[1]["status"] == "COMPLETED"
    assert any(o["id"] == order[1]["id"] for o in hist[1])
    print("LIVE DOGFOOD: OK  (menu=%s customer=%s reservation=%s order=%s completed=%s history=%s)"
          % (menu[0], alice[0], res[0], order[0], upd[0], hist[0]))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()