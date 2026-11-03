SQL files in this folder run once, in alphabetical order, the first time the
PostgreSQL container starts with an empty volume (e.g. `01-schema.sql`).

The schema is the issue "Design PostgreSQL schema" (Member 1).
To re-run the scripts after changing them: `docker compose down -v` (deletes the data).
