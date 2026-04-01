FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ARG TARGETARCH

# ── Install runtime dependencies ──────────────────────────────
RUN apt-get update && apt-get install -y \
    libevent-dev libboost-dev libsqlite3-dev libzmq3-dev \
    python3 python3-pip jq curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Download Bitcoin Core v27.0 pre-built binary ──────────────
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) ARCH="x86_64-linux-gnu" ;; \
      arm64) ARCH="aarch64-linux-gnu" ;; \
      *)     echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac; \
    curl -fsSL "https://bitcoincore.org/bin/bitcoin-core-27.0/bitcoin-27.0-${ARCH}.tar.gz" \
      -o /tmp/bitcoin.tar.gz && \
    tar -xzf /tmp/bitcoin.tar.gz -C /tmp && \
    install -m 0755 /tmp/bitcoin-27.0/bin/bitcoind    /usr/local/bin/ && \
    install -m 0755 /tmp/bitcoin-27.0/bin/bitcoin-cli  /usr/local/bin/ && \
    install -m 0755 /tmp/bitcoin-27.0/bin/bitcoin-util /usr/local/bin/ && \
    rm -rf /tmp/bitcoin*

# ── Download the signet miner script + test_framework ─────────
# The miner script resolves test_framework relative to its location:
#   contrib/signet/miner -> ../../test/functional/test_framework
# So we preserve the source tree layout under /opt/bitcoin/
RUN curl -fsSL "https://github.com/bitcoin/bitcoin/archive/refs/tags/v27.0.tar.gz" \
      -o /tmp/src.tar.gz && \
    mkdir -p /opt/bitcoin/contrib/signet /opt/bitcoin/test/functional && \
    tar -xzf /tmp/src.tar.gz -C /tmp && \
    cp /tmp/bitcoin-27.0/contrib/signet/miner /opt/bitcoin/contrib/signet/miner && \
    cp -r /tmp/bitcoin-27.0/test/functional/test_framework /opt/bitcoin/test/functional/test_framework && \
    chmod +x /opt/bitcoin/contrib/signet/miner && \
    ln -sf /opt/bitcoin/contrib/signet/miner /usr/local/bin/miner && \
    rm -rf /tmp/src.tar.gz /tmp/bitcoin-27.0

RUN pip3 install requests

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 38332 38333

ENTRYPOINT ["/entrypoint.sh"]
