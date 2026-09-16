-- Install the extension in the database created by the Postgres image entrypoint.

CREATE EXTENSION IF NOT EXISTS pg_textsearch;
