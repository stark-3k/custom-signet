"""
Custom Signet Faucet
────────────────────
Flask service that dispenses signet BTC to any address.
Uses the same "miner" wallet as the miner controller.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

# ── Configuration ───────────────────────────────────────────
RPC_USER = os.environ.get("BITCOIN_RPC_USER", "signet")
RPC_PASS = os.environ.get("BITCOIN_RPC_PASS", "signetpass")
RPC_HOST = os.environ.get("BITCOIN_RPC_HOST", "bitcoin")
RPC_PORT = os.environ.get("BITCOIN_RPC_PORT", "38332")
DATADIR = "/bitcoin-data"
STATE_FILE = f"{DATADIR}/.signet-state.json"
MAX_AMOUNT = float(os.environ.get("FAUCET_MAX_AMOUNT", "1"))
MEMPOOL_URL = os.environ.get("MEMPOOL_URL", "")

CLI_CMD = (
    f"bitcoin-cli -datadir={DATADIR} "
    f"-rpcconnect={RPC_HOST} -rpcport={RPC_PORT} "
    f"-rpcuser={RPC_USER} -rpcpassword={RPC_PASS}"
)

# Recent dispensed transactions (in-memory)
recent_txs = []
signet_challenge = ""


def load_signet_challenge():
    global signet_challenge
    conf = f"{DATADIR}/bitcoin.conf"
    for _ in range(60):
        if os.path.exists(conf):
            break
        time.sleep(2)
    try:
        with open(conf) as f:
            for line in f:
                if line.strip().startswith("signetchallenge="):
                    signet_challenge = line.strip().split("=", 1)[1]
                    print(f"Signet challenge: {signet_challenge}", flush=True)
                    return
    except Exception as e:
        print(f"Could not read signet challenge: {e}", flush=True)


# ── Helpers ─────────────────────────────────────────────────
def rpc(method, *params):
    cmd = f'{CLI_CMD} {method} {" ".join(str(p) for p in params)}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    out = result.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


def wait_for_node():
    print("Waiting for Bitcoin Core RPC...", flush=True)
    for _ in range(120):
        try:
            rpc("getblockchaininfo")
            print("Bitcoin Core is ready.", flush=True)
            return True
        except Exception:
            time.sleep(2)
    raise RuntimeError("Bitcoin Core did not become ready in time")


def load_wallet():
    for _ in range(60):
        if os.path.exists(STATE_FILE):
            break
        time.sleep(2)

    for attempt in range(30):
        try:
            wallets = rpc("listwallets")
            if "miner" not in wallets:
                rpc("loadwallet", "miner")
            print("Wallet 'miner' loaded successfully.", flush=True)
            return
        except Exception as e:
            print(f"Wallet load attempt {attempt+1}/30 failed: {e}", flush=True)
            time.sleep(2)
    print("WARNING: Could not load wallet after 30 attempts!", flush=True)


# ── Routes ──────────────────────────────────────────────────
@app.route("/")
def index():
    return send_file("/app/index.html")


@app.route("/api/faucet", methods=["POST"])
def faucet_send():
    data = request.get_json(force=True, silent=True) or {}
    address = data.get("address", "").strip()
    amount = data.get("amount", 1.0)

    if not address:
        return jsonify({"ok": False, "error": "Address is required"}), 400

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if amount < 0.001 or amount > MAX_AMOUNT:
        return jsonify({"ok": False, "error": f"Amount must be between 0.001 and {MAX_AMOUNT} BTC"}), 400

    try:
        txid = rpc("sendtoaddress", address, f"{amount:.8f}")
        entry = {
            "address": address,
            "amount": amount,
            "txid": txid,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        recent_txs.insert(0, entry)
        if len(recent_txs) > 50:
            recent_txs.pop()

        print(f"Sent {amount} BTC to {address} — txid: {txid}", flush=True)
        return jsonify({"ok": True, "txid": txid, "amount": amount, "address": address})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/faucet/balance")
def faucet_balance():
    try:
        bal = rpc("getbalance")
        return jsonify({"ok": True, "balance": float(bal)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/faucet/recent")
def faucet_recent():
    return jsonify({"ok": True, "transactions": recent_txs[:20]})


@app.route("/api/faucet/config")
def faucet_config():
    return jsonify({"ok": True, "mempool_url": MEMPOOL_URL, "max_amount": MAX_AMOUNT, "signet_challenge": signet_challenge})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    load_signet_challenge()
    wait_for_node()
    load_wallet()
    print("Faucet ready on :5090", flush=True)
    app.run(host="0.0.0.0", port=5090, debug=False)
