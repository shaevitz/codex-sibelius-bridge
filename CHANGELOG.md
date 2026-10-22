# Changelog

## 1.2.0 — 2026-10-21

- Batch independent complete-bar voice rebuilds under one recovery copy and full observed-score before/after guard. Reject mixed scalar/rebuild batches and multiple voices in the same staff/bar.
- Restore and verify grace offsets after the complete rebuilt voice has settled, preventing later grace/beam construction from moving earlier graces.
- Export selected PDFs with one shared native inventory (`export-set`), and show a uniquely selected dynamic part directly (`show-part`).
- Add `export-proof` for fast read-only PDF output without a musical inventory. Results explicitly cannot be edit baselines. All selectors are preflighted; every PDF must open and is counted/hashed.
- Resolve checkout symlinks consistently so CLI installation and module imports agree on the loaded native build.
- Add non-invoking local `status`, configurable waits and a 1,800-second default for running jobs. Timeout messages preserve the original invocation identity and prohibit blind retries.
- Publish previously local part-context graphical overrides and exact music-text/bold-Roman formatting checks.
- Add optional rendered-page comparison and a complete-score review workflow emphasizing musical acceptance, cross-part batching and changed-passage proof.
- Keep optional unsafe L.V./incoming-tie APIs, private fixture helpers, score data and the failed experimental direct-resize adapter out of the public package.

See VALIDATION.md for actual tests and limits. This release does not claim a faster complete snapshot scanner or full playback fidelity.

## 1.1.0 and earlier

Initial public bridge, guarded native edits, explicit voice recipes, recovery, PDF exports, brass/percussion scope and MIT source distribution. Later fixes checked line playback against Sibelius's eight supported repeat passes.
