FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ARG TARGETARCH

RUN apt-get update && apt-get install -y \
    python3 python3-pip jq curl ca-certificates \
    libevent-dev libboost-dev libsqlite3-dev libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install flask flask-cors requests

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
    install -m 0755 /tmp/bitcoin-27.0/bin/bitcoin-cli  /usr/local/bin/ && \
    install -m 0755 /tmp/bitcoin-27.0/bin/bitcoin-util /usr/local/bin/ && \
    rm -rf /tmp/bitcoin*

# ── Download the signet miner script + test_framework ─────────
RUN curl -fsSL "https://github.com/bitcoin/bitcoin/archive/refs/tags/v27.0.tar.gz" \
      -o /tmp/src.tar.gz && \
    mkdir -p /opt/bitcoin/contrib/signet /opt/bitcoin/test/functional && \
    tar -xzf /tmp/src.tar.gz -C /tmp && \
    cp /tmp/bitcoin-27.0/contrib/signet/miner /opt/bitcoin/contrib/signet/miner && \
    cp -r /tmp/bitcoin-27.0/test/functional/test_framework /opt/bitcoin/test/functional/test_framework && \
    chmod +x /opt/bitcoin/contrib/signet/miner && \
    ln -sf /opt/bitcoin/contrib/signet/miner /usr/local/bin/miner && \
    rm -rf /tmp/src.tar.gz /tmp/bitcoin-27.0

WORKDIR /app
COPY miner_controller.py /app/

EXPOSE 5080

CMD ["python3", "/app/miner_controller.py"]
