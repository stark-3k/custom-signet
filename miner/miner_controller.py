"""
Custom Signet Miner Controller
─────────────────────────────
Flask API that wraps the official signet miner script.

Uses --ongoing mode which manages block timestamps internally
to keep difficulty stable at the target nbits. Blocks arrive
at ~10 min intervals with --min-nbits.

Also supports manual single-block mining for on-demand use
during demos (e.g. to confirm a pending transaction immediately).
"""

import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Configuration ───────────────────────────────────────────
RPC_USER = os.environ.get("BITCOIN_RPC_USER", "signet")
RPC_PASS = os.environ.get("BITCOIN_RPC_PASS", "signetpass")
RPC_HOST = os.environ.get("BITCOIN_RPC_HOST", "bitcoin")
RPC_PORT = os.environ.get("BITCOIN_RPC_PORT", "38332")
DATADIR = "/bitcoin-data"
STATE_FILE = f"{DATADIR}/.signet-state.json"

CLI_CMD = (
    f"bitcoin-cli -datadir={DATADIR} "
    f"-rpcconnect={RPC_HOST} -rpcport={RPC_PORT} "
    f"-rpcuser={RPC_USER} -rpcpassword={RPC_PASS}"
)
GRINDER = "bitcoin-util grind"


# ── Global State ────────────────────────────────────────────
class MinerState:
    def __init__(self):
        self.running = False
        self.mode = None  # "ongoing" or "fast"
        self.ongoing_process = None
        self.monitor_thread = None
        self.fast_stop = threading.Event()
        self.blocks_mined = 0
        self.last_block_time = None
        self.last_block_hash = None
        self.last_block_height = None
        self.errors = []
        self.miner_address = None
        self.start_time = None
        self.lock = threading.Lock()

    def to_dict(self):
        with self.lock:
            return {
                "running": self.running,
                "mode": self.mode,
                "blocks_mined": self.blocks_mined,
                "last_block_time": self.last_block_time,
                "last_block_hash": self.last_block_hash,
                "last_block_height": self.last_block_height,
                "miner_address": self.miner_address,
                "start_time": self.start_time,
                "recent_errors": self.errors[-5:],
            }


state = MinerState()


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


def load_signet_state():
    for _ in range(60):
        if os.path.exists(STATE_FILE):
            break
        time.sleep(2)

    with open(STATE_FILE) as f:
        signet_state = json.load(f)

    state.miner_address = signet_state["miner_address"]

    for attempt in range(30):
        try:
            wallets = rpc("listwallets")
            if "miner" not in wallets:
                rpc("loadwallet", "miner")
            print(f"Wallet 'miner' loaded successfully.", flush=True)
            break
        except Exception as e:
            print(f"Wallet load attempt {attempt+1}/30 failed: {e}", flush=True)
            time.sleep(2)
    else:
        print("WARNING: Could not load wallet after 30 attempts!", flush=True)

    print(f"Miner address: {state.miner_address}", flush=True)


def update_chain_info():
    try:
        info = rpc("getblockchaininfo")
        best = rpc("getbestblockhash")
        with state.lock:
            state.last_block_hash = best
            state.last_block_height = info.get("blocks", 0)
            state.last_block_time = datetime.now(timezone.utc).isoformat()
    except Exception:
        pass


def monitor_ongoing():
    """Poll the chain for new blocks while --ongoing runs."""
    last_height = 0
    try:
        info = rpc("getblockchaininfo")
        last_height = info.get("blocks", 0)
    except Exception:
        pass

    while state.running and state.ongoing_process:
        if state.ongoing_process.poll() is not None:
            stderr = ""
            try:
                stderr = state.ongoing_process.stderr.read()
            except Exception:
                pass
            with state.lock:
                state.running = False
                state.errors.append(
                    f"{datetime.now(timezone.utc).isoformat()} — "
                    f"Miner exited (code {state.ongoing_process.returncode}): {stderr}"
                )
            print(f"Miner process exited: {stderr}", flush=True)
            break

        try:
            info = rpc("getblockchaininfo")
            current_height = info.get("blocks", 0)
            if current_height > last_height:
                new_blocks = current_height - last_height
                best = rpc("getbestblockhash")
                with state.lock:
                    state.blocks_mined += new_blocks
                    state.last_block_hash = best
                    state.last_block_height = current_height
                    state.last_block_time = datetime.now(timezone.utc).isoformat()
                print(f"Block #{current_height} | {best[:16]}...", flush=True)
                last_height = current_height
        except Exception:
            pass

        time.sleep(5)


def fast_mine_loop(interval):
    """Mine a block every `interval` seconds until stopped."""
    print(f"Fast mining started (every {interval}s)", flush=True)
    while not state.fast_stop.is_set():
        cmd = (
            f'miner --cli "{CLI_CMD}" generate '
            f"--address {state.miner_address} "
            f'--grind-cmd "{GRINDER}" '
            f"--min-nbits "
            f"--set-block-time {int(time.time())}"
        )
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                with state.lock:
                    state.errors.append(f"{datetime.now(timezone.utc).isoformat()} — Fast mine error: {err}")
                print(f"Fast mine error: {err}", flush=True)
            else:
                info = rpc("getblockchaininfo")
                best = rpc("getbestblockhash")
                with state.lock:
                    state.blocks_mined += 1
                    state.last_block_hash = best
                    state.last_block_height = info.get("blocks", 0)
                    state.last_block_time = datetime.now(timezone.utc).isoformat()
                print(f"Fast block #{info.get('blocks', '?')} | {best[:16]}...", flush=True)
        except Exception as e:
            with state.lock:
                state.errors.append(f"{datetime.now(timezone.utc).isoformat()} — Fast mine exception: {e}")
            print(f"Fast mine exception: {e}", flush=True)

        state.fast_stop.wait(interval)

    with state.lock:
        state.running = False
        state.mode = None
        state.start_time = None
    print("Fast mining stopped.", flush=True)


# ── API Endpoints ───────────────────────────────────────────
@app.route("/api/status")
def api_status():
    data = state.to_dict()
    try:
        chain = rpc("getblockchaininfo")
        mempool = rpc("getmempoolinfo")
        net = rpc("getnetworkinfo")
        peers = rpc("getpeerinfo")
        data["node"] = {
            "chain": chain.get("chain"),
            "blocks": chain.get("blocks"),
            "difficulty": chain.get("difficulty"),
            "bestblockhash": chain.get("bestblockhash"),
            "size_on_disk": chain.get("size_on_disk"),
            "mempool_size": mempool.get("size", 0),
            "mempool_bytes": mempool.get("bytes", 0),
            "connections": len(peers) if isinstance(peers, list) else 0,
            "version": net.get("subversion"),
        }
    except Exception as e:
        data["node"] = {"error": str(e)}
    return jsonify(data)


@app.route("/api/start", methods=["POST"])
def api_start():
    """Start --ongoing mining. Stable difficulty, ~10 min blocks."""
    if state.running:
        return jsonify({"ok": False, "message": "Already running"})

    cmd = (
        f'miner --cli "{CLI_CMD}" generate '
        f"--address {state.miner_address} "
        f'--grind-cmd "{GRINDER}" '
        f"--min-nbits "
        f"--ongoing"
    )

    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        state.ongoing_process = proc
        state.running = True
        state.mode = "ongoing"
        state.start_time = datetime.now(timezone.utc).isoformat()

        state.monitor_thread = threading.Thread(target=monitor_ongoing, daemon=True)
        state.monitor_thread.start()

        return jsonify({
            "ok": True,
            "message": "Mining started (--ongoing, stable difficulty, ~10 min blocks)"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Stop any running miner (ongoing or fast)."""
    if not state.running:
        return jsonify({"ok": False, "message": "Not running"})

    # Stop ongoing miner process
    if state.ongoing_process and state.ongoing_process.poll() is None:
        try:
            os.kill(state.ongoing_process.pid, signal.SIGTERM)
            state.ongoing_process.wait(timeout=10)
        except Exception:
            try:
                os.kill(state.ongoing_process.pid, signal.SIGKILL)
            except Exception:
                pass

    # Stop fast miner thread
    state.fast_stop.set()

    state.running = False
    state.mode = None
    state.ongoing_process = None
    state.start_time = None
    return jsonify({"ok": True, "message": "Mining stopped"})


@app.route("/api/start-fast", methods=["POST"])
def api_start_fast():
    """Start fast mining — one block every N seconds (default 30)."""
    if state.running:
        return jsonify({"ok": False, "message": "Already running"})

    data = request.get_json(force=True, silent=True) or {}
    interval = max(5, min(300, int(data.get("interval", 30))))

    state.running = True
    state.mode = "fast"
    state.start_time = datetime.now(timezone.utc).isoformat()
    state.fast_stop = threading.Event()

    t = threading.Thread(target=fast_mine_loop, args=(interval,), daemon=True)
    t.start()

    return jsonify({
        "ok": True,
        "message": f"Fast mining started (1 block every {interval}s)"
    })


@app.route("/api/mine-once", methods=["POST"])
def api_mine_once():
    """
    Mine a single block NOW with real timestamp.
    Great for demos — confirm a pending tx on demand.
    """
    cmd = (
        f'miner --cli "{CLI_CMD}" generate '
        f"--address {state.miner_address} "
        f'--grind-cmd "{GRINDER}" '
        f"--min-nbits "
        f"--set-block-time {int(time.time())}"
    )

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())

        info = rpc("getblockchaininfo")
        best = rpc("getbestblockhash")

        with state.lock:
            state.blocks_mined += 1
            state.last_block_time = datetime.now(timezone.utc).isoformat()
            state.last_block_hash = best
            state.last_block_height = info.get("blocks", 0)

        return jsonify({
            "ok": True,
            "block_height": info.get("blocks"),
            "block_hash": best,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/balance")
def api_balance():
    try:
        bal = rpc("getbalance")
        return jsonify({"ok": True, "balance": float(bal)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/recent-blocks")
def api_recent_blocks():
    count = min(int(request.args.get("n", 10)), 50)
    try:
        height = rpc("getblockchaininfo")["blocks"]
        blocks = []
        for i in range(count):
            h = height - i
            if h < 0:
                break
            bh = rpc("getblockhash", h)
            header = rpc("getblockheader", bh)
            blocks.append({
                "height": h,
                "hash": bh,
                "time": header.get("time"),
                "nTx": header.get("nTx"),
                "size": header.get("size"),
                "difficulty": header.get("difficulty"),
            })
        return jsonify({"ok": True, "blocks": blocks})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    wait_for_node()
    load_signet_state()
    update_chain_info()
    print("Miner controller ready on :5080", flush=True)
    app.run(host="0.0.0.0", port=5080, debug=False)
