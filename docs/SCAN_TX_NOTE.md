# Scan Transaction Discipline — Note

## Current state

`app/indexer/scan.py` runs `DELETE` + `INSERT` for every photo inside one
implicit transaction. `conn.commit()` fires once at the end of `run_scan()`,
after the full `_walk_photos()` traversal.

## Why flagged

`app/indexer/CLAUDE.md` mandates short transactions in indexer steps:

> Never `BEGIN; ...long work...; COMMIT;` in these steps. Short transactions only.

Embed and caption commit per row to release the SQLite write lock between
rows, allowing the two pipelines to interleave under WAL. Scan currently
violates that pattern.

## Real-world impact

- **Lock contention**: if scan runs concurrently with caption/embed (separate
  process), those steps block on scan's commit. WAL lets readers proceed but
  serializes writers.
- **Crash safety**: less severe than first claimed. A crash before final
  commit rolls back every pending DELETE+INSERT — original rows survive,
  but all scan progress is wasted.
- **WAL growth**: long-running tx on 100K photos keeps WAL frames pinned
  until commit.

## Why deferred

- Scan typically runs alone; concurrent caption/embed during scan is not the
  common path.
- Per-row commit slows scan slightly (fsync per row) — may want batched
  commits (e.g. every 100 rows) instead of per-row.
- Wants explicit decision on batch size before changing behavior.

## Options when revisited

1. Per-row `conn.commit()` — matches `embed.py` exactly.
2. Batch commit every N rows (e.g. 100) — compromise between lock release
   and fsync overhead.
3. Leave as-is and document scan as "run alone" in `docs/INDEXING.md`.
