---
name: deployment-status
description: Read-only alignment of local HEAD, origin/main, dirty tree, and any proven Modal/Vercel/migration state.
---

# /deployment-status

Read-only. Invoke the `deployment-alignment` skill.

Do not deploy, migrate, push, or mutate Appwrite, Modal, Vercel, or databases.

Compare local HEAD, `origin/main`, dirty tree, Modal build SHA, Vercel deployment, migration state, and persistence mode. Grade each row `DEPLOYED` / `COMMITTED` / `UNCOMMITTED` / `INFERRED` / `UNVERIFIED`.

The current uncommitted P0 / Change Set C tree is `UNCOMMITTED` unless also present on the compared ref.
