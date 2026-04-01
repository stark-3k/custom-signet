# Custom Bitcoin Signet — Full Stack

Custom signet node + miner + control panel + mempool.space + Caddy reverse proxy.

```
                    ┌──────────────────────────────────────┐
                    │           Caddy (reverse proxy)       │
Internet ──────────▶│  :80/:443 → Control Panel + /api/    │
                    │  :8080    → Mempool.space             │
                    │  (auto HTTPS when domain configured)  │
                    └────────┬──────────────┬───────────────┘
                             │              │
                    ┌────────▼──┐  ┌────────▼───────┐
                    │ UI  │ API │  │  Mempool FE/BE │
                    └──┬────┬───┘  └───────┬────────┘
                       │    │              │
                       │  ┌─▼──────────┐ ┌─▼──────┐
                       │  │   Miner    │ │ Electrs │
                       │  └─────┬──────┘ └────┬────┘
                       │        │              │
                    ┌──▼────────▼──────────────▼────┐
                    │        Bitcoin Core            │
                    │   :38333 (P2P)  :38332 (RPC)  │
                    └───────────────────────────────┘
```

## VPS Requirements

- Ubuntu 22.04+ (or any Linux with Docker)
- 4+ GB RAM (for compiling Bitcoin Core)
- 10 GB disk
- Docker Engine + Docker Compose v2

## Quick Start (IP only, HTTP)

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in, then:

# 2. Upload and extract
tar -xzf custom-signet.tar.gz
cd custom-signet

# 3. Build and start (first run: 15-30 min)
docker compose up --build -d

# 4. Watch bootstrap
docker compose logs -f bitcoin
# Wait for "BOOTSTRAP COMPLETE", then:
docker compose logs -f miner
```

Open in your browser:
- **Control Panel:** `http://YOUR_VPS_IP`
- **Mempool.space:** `http://YOUR_VPS_IP:8080`

## Setup with a Domain (automatic HTTPS)

Point two DNS records at your VPS:
```
signet.yourdomain.com    → YOUR_VPS_IP
mempool.signet.yourdomain.com → YOUR_VPS_IP
```

Edit `.env`:
```env
SITE_ADDRESS=signet.yourdomain.com
MEMPOOL_ADDRESS=mempool.signet.yourdomain.com
```

Then start as normal — Caddy gets Let's Encrypt certs automatically:
```bash
docker compose up --build -d
```

Now accessible at:
- **Control Panel:** `https://signet.yourdomain.com`
- **Mempool.space:** `https://mempool.signet.yourdomain.com`

## Firewall

```bash
sudo ufw allow 80/tcp      # HTTP (Caddy)
sudo ufw allow 443/tcp     # HTTPS (Caddy)
sudo ufw allow 8080/tcp    # Mempool (IP-only mode)
sudo ufw allow 38333/tcp   # Bitcoin P2P (for external nodes)
```

Bitcoin RPC (38332) is bound to localhost only — not exposed to the internet.

## Mining

**Auto mining:** Click "Start Auto-Mining" in the control panel. Blocks
arrive every ~10 minutes with stable difficulty. Runs indefinitely.

**On-demand:** Click "Mine 1 Block Now" to instantly confirm a pending
transaction. Perfect for demos.

## Connecting External Nodes

```bash
# Get your signet challenge:
docker exec signet-bitcoin cat /bitcoin-data/bitcoin.conf | grep signetchallenge

# On the external node's bitcoin.conf:
signet=1
[signet]
signetchallenge=<value>
addnode=YOUR_VPS_IP:38333
```

## Sending Transactions

```bash
docker exec signet-bitcoin bitcoin-cli \
  -datadir=/bitcoin-data -rpcuser=signet -rpcpassword=signetpass \
  sendtoaddress <address> <amount>
```

## API Reference

All endpoints are at `/api/` on the control panel URL.

```
GET  /api/status         Node + miner status
POST /api/start          Start auto-mining (--ongoing)
POST /api/stop           Stop mining
POST /api/mine-once      Mine one block immediately
GET  /api/balance        Miner wallet balance
GET  /api/recent-blocks  Last N blocks (?n=10)
```

## Troubleshooting

**Build OOM on small VPS:**
Edit `bitcoin/Dockerfile` and `miner/Dockerfile` — change `make -j$(nproc)` to `make -j1`

**Mempool stuck on "Loading":**
Electrs needs to finish indexing. Check: `docker compose logs -f electrs`

**Caddy not getting certs:**
Ensure ports 80 and 443 are open AND your DNS records are pointing to the VPS.

**Reset everything:**
```bash
docker compose down -v
docker compose up --build -d
```

## File Structure

```
custom-signet/
├── .env                    # Domain / IP config
├── docker-compose.yml      # All services
├── caddy/
│   └── Caddyfile           # Reverse proxy routes
├── bitcoin/
│   ├── Dockerfile          # Builds Bitcoin Core v27 from source
│   └── entrypoint.sh       # Bootstrap (keygen → challenge → genesis)
├── miner/
│   ├── Dockerfile          # Miner controller image
│   └── miner_controller.py # Flask API wrapping signet miner
├── ui/
│   ├── Dockerfile          # Nginx serving the dashboard
│   ├── nginx.conf          # Internal /api proxy
│   └── index.html          # Control panel
└── README.md
```
