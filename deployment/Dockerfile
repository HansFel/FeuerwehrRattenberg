# Dockerfile für die FF-Rattenberg-Wettbewerbs-App (120 Jahre Feuerwehr)
FROM python:3.13-slim

# Systempakete: Build-Tools für psycopg2, Postgres-Client fürs Warten auf die DB
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev postgresql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/wettbewerb

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app/ ./app/
COPY run.py ./

ARG COMMIT_HASH=dev
ENV COMMIT_HASH=${COMMIT_HASH}

EXPOSE 8000

COPY deployment/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r//' /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
