#!/usr/bin/env bash
# Package the whole app (database with data, backend, frontend) for another machine.
#
#   ./scripts/bundle.sh          → bundle/ (copy this folder to a USB drive)
#
# Needs the local database running with the indexed corpus (docker compose up -d db).
# The bundle contains no secrets: put your own .env next to docker-compose.yml on the target.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "1/4 Dumping the database (corpus, embeddings, answer cache)..."
docker compose exec -T db pg_dump -U paragraf -d paragraf --no-owner --no-privileges \
  --exclude-table-data=usage_daily --exclude-table-data=ip_usage_daily \
  | gzip -9 > docker/db/paragraf.sql.gz

echo "2/4 Building images..."
docker compose -f docker-compose.bundle.yml build

echo "3/4 Saving images to bundle/paragraf-images.tar.gz (takes a few minutes)..."
rm -rf bundle && mkdir -p bundle
docker save paragraf-db:latest paragraf-api:latest paragraf-web:latest \
  | gzip -6 > bundle/paragraf-images.tar.gz

echo "4/4 Writing the run files..."
# The target machine only runs the loaded images, so the build: lines go.
grep -v '^\s*build:' docker-compose.bundle.yml > bundle/docker-compose.yml
cp .env.example bundle/.env.example
cat > bundle/README.txt <<'EOF'
Asystent Prawa Pracy - portable bundle

Requirements: Docker with Docker Compose, internet access (OpenAI and Jina APIs).

1. Load the images (once):
     docker load -i paragraf-images.tar.gz
2. Create .env next to docker-compose.yml: copy .env.example to .env and fill in
   OPENAI_API_KEY and JINA_API_KEY (DATABASE_URL is set by docker-compose.yml).
3. Start:
     docker compose up -d
   First start loads the database (about a minute). Then open http://localhost:8080
4. Stop:   docker compose down        (keeps the database)
   Reset:  docker compose down -v     (deletes the database; it reloads on next start)
EOF

ls -lh bundle
echo "Done. Copy the bundle/ folder to the USB drive."
