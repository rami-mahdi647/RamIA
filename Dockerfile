FROM python:3.11-slim

WORKDIR /app

# (Opcional) dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY . .

# Tu proyecto es casi todo stdlib; si luego metes FastAPI/cryptography, aquí instalarías requirements.txt
# RUN pip install --no-cache-dir -r requirements.txt

# Persistencia de chain data
VOLUME ["/app/aichain_data", "/app/logs"]

# Arranca el loop de minado/nodo
CMD ["bash", "run_node.sh", "miner_1"]
