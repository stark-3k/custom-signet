FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ARG TARGETARCH

RUN apt-get update && apt-get install -y \
    python3 python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install flask flask-cors requests

# ── Download bitcoin-cli only ─────────────────────────────────
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) ARCH="x86_64-linux-gnu" ;; \
      arm64) ARCH="aarch64-linux-gnu" ;; \
      *)     echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac; \
    curl -fsSL "https://bitcoincore.org/bin/bitcoin-core-27.0/bitcoin-27.0-${ARCH}.tar.gz" \
      -o /tmp/bitcoin.tar.gz && \
    tar -xzf /tmp/bitcoin.tar.gz -C /tmp && \
    install -m 0755 /tmp/bitcoin-27.0/bin/bitcoin-cli /usr/local/bin/ && \
    rm -rf /tmp/bitcoin*

WORKDIR /app
COPY faucet_server.py /app/
COPY index.html /app/

EXPOSE 5090

CMD ["python3", "/app/faucet_server.py"]
