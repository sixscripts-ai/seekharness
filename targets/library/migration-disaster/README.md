# Migration Disaster

`migrations.py` receives databases at schema version 1. Migrate them to version 3. Final `users` columns: `id`, `email`, `display_name`, `active`. Preserve rows, default `display_name` from the email local-part, default `active` to 1, and make migration idempotent.
