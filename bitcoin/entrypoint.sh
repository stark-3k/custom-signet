#!/bin/bash
set -euo pipefail

DATADIR="/bitcoin-data"
CONF="$DATADIR/bitcoin.conf"
STATE="$DATADIR/.signet-initialized"
RPC_USER="${BITCOIN_RPC_USER:-signet}"
RPC_PASS="${BITCOIN_RPC_PASS:-signetpass}"

CLI="bitcoin-cli -datadir=$DATADIR -rpcuser=$RPC_USER -rpcpassword=$RPC_PASS"
GRINDER="bitcoin-util grind"

# ─── First-time bootstrap ──────────────────────────────────
if [ ! -f "$STATE" ]; then
    echo "╔══════════════════════════════════════════════╗"
    echo "║   BOOTSTRAPPING CUSTOM SIGNET                ║"
    echo "╚══════════════════════════════════════════════╝"

    # 1) Start a temporary regtest node to generate keys
    echo "[1/7] Starting temporary regtest node..."
    cat > "$CONF" <<EOF
regtest=1
[regtest]
rpcuser=$RPC_USER
rpcpassword=$RPC_PASS
rpcallowip=0.0.0.0/0
rpcbind=0.0.0.0
EOF
    bitcoind -datadir="$DATADIR" -daemon
    sleep 5

    # 2) Create signer wallet & get descriptors
    echo "[2/7] Creating signer wallet..."
    $CLI -regtest createwallet "signer" >/dev/null 2>&1

    echo "[3/7] Exporting descriptors..."
    DESCRIPTORS=$($CLI -regtest listdescriptors true | jq -c '.descriptors')

    # 3) Generate signet challenge address
    echo "[4/7] Generating signet challenge..."
    ADDR=$($CLI -regtest getnewaddress "" bech32)
    SIGNET_CHALLENGE=$($CLI -regtest getaddressinfo "$ADDR" | jq -r '.scriptPubKey')

    echo "       Challenge: $SIGNET_CHALLENGE"
    echo "       Address:   $ADDR"

    # 4) Stop regtest
    $CLI -regtest stop || true
    sleep 3

    # 5) Clean regtest data, write signet config
    echo "[5/7] Switching to signet mode..."
    rm -rf "$DATADIR/regtest"

    cat > "$CONF" <<EOF
signet=1

[signet]
rpcuser=$RPC_USER
rpcpassword=$RPC_PASS
rpcallowip=0.0.0.0/0
rpcbind=0.0.0.0
rpcport=38332
port=38333
signetchallenge=$SIGNET_CHALLENGE
txindex=1
server=1
rest=1
zmqpubrawblock=tcp://0.0.0.0:28332
zmqpubrawtx=tcp://0.0.0.0:28333
fallbackfee=0.0001
EOF

    # 6) Start signet, import keys, mine genesis
    echo "[6/7] Starting signet node..."
    bitcoind -datadir="$DATADIR" -daemon
    sleep 5

    echo "       Creating miner wallet & importing keys..."
    $CLI createwallet "miner" >/dev/null 2>&1
    $CLI importdescriptors "$DESCRIPTORS" >/dev/null 2>&1

    MINER_ADDR=$($CLI getnewaddress "" bech32)

    echo "       Mining genesis block..."
    miner --cli "$CLI" generate \
        --address "$MINER_ADDR" \
        --grind-cmd "$GRINDER" \
        --min-nbits \
        --set-block-time "$(date +%s)"

    echo "[7/7] Saving state..."
    # Persist state for the miner service
    cat > "$DATADIR/.signet-state.json" <<EOFJ
{
    "signet_challenge": "$SIGNET_CHALLENGE",
    "miner_address": "$MINER_ADDR",
    "descriptors": $DESCRIPTORS
}
EOFJ

    touch "$STATE"
    $CLI stop || true
    sleep 3

    echo "╔══════════════════════════════════════════════╗"
    echo "║   BOOTSTRAP COMPLETE — STARTING NODE         ║"
    echo "╚══════════════════════════════════════════════╝"
fi

# ─── Normal startup ─────────────────────────────────────────
echo "Starting Bitcoin Core (custom signet)..."
exec bitcoind -datadir="$DATADIR" -printtoconsole
