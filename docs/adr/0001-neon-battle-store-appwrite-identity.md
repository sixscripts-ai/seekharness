# Neon holds official battle state; Appwrite is identity only

Older docs, Strike outcomes, and a still-live code path treat Appwrite Documents as a battle store. As-built HEAD defaults battles, events, scores, Elo, and official results to Neon (`PERSISTENCE_BACKEND=postgres`). Appwrite is the player identity provider (JWT / `Account.get()`). Dual-write and read-fallback stay off so the two stores cannot split. The Appwrite document branch remains in the tree for tests and emergency rollback; it is not the system of record.
