# Simulator for docker-compose. Build context is the repo root.
FROM python:3.11.11-slim
WORKDIR /app
COPY arbitrage/requirements.txt arbitrage/requirements.txt
RUN pip install --no-cache-dir -r arbitrage/requirements.txt
COPY arbitrage arbitrage
COPY db db
ENTRYPOINT ["python", "-m", "arbitrage.run"]
CMD ["--start", "2026-10-01", "--end", "2026-10-07", "--node", "PECO"]
