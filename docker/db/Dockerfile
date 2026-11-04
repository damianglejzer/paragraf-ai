# Postgres + pgvector with the Paragraf corpus preloaded (for the portable bundle).
# paragraf.sql.gz is produced by scripts/bundle.sh (pg_dump of the local database). Postgres
# runs everything in /docker-entrypoint-initdb.d/ once, when the data volume is empty.
FROM pgvector/pgvector:pg16
COPY paragraf.sql.gz /docker-entrypoint-initdb.d/10-paragraf.sql.gz
