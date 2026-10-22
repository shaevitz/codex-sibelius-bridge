# Validation status

## Version 1.2.0 — October 21, 2026

31 controller and transport regression tests pass. They cover independent rhythm batches, recipe immutability, unrelated-object preservation, part-context isolation, exact formatted text, complete multi-PDF validation, proof-only baseline refusal, missing/corrupt PDFs, timeout behavior, checkout-symlink installation and the result transport. CI installs the Python dependencies and runs on Python 3.11/3.13 with Node 22.

The generated public build was installed and loaded in Sibelius 2025.12.1 on macOS. Its version/build and Unicode/empty-field protocol checks pass. Native acceptance used a disposable 23-staff, 32-bar extract with 2,788 observed objects:

- Three PDF-only exports completed in about 1.2 seconds, without a full inventory or recovery/candidate file. The result explicitly cannot be an edit baseline.
- A request with a valid part followed by a missing part was refused before any PDF was written.
- The comparable three-part guarded export completed in about 14.4 seconds; all observed fixture facts remained identical. Rendered outputs checked from both paths match.
- Direct part switching opened the named part and PDF output restored its prior context.
- A full-size read-only benchmark exported 20 parts/231 pages from a 23-staff, 478-bar score in about 19.4 seconds. The saved file hash remained unchanged. This is PDF-output acceptance, not a new full native musical comparison.
- The page comparator detected a synthetic page-count mismatch.

The rhythm batching and grace-position fixes were previously accepted natively on disposable fixtures and used in full-score brass/percussion work with exact observed-score guards and source-PDF proofs. Their mutation implementation is ported from the validated local 1.1.4 core. The experimental direct-resize adapter was withdrawn after runtime failures and is not included. No new structural mutation or unsafe optional getter was added for 1.2.0.

These timings describe these files on one Mac. This release avoids unnecessary scans during PDF proof output; it does not claim a faster complete snapshot scanner. It does not certify all supported-looking combinations, specialist notation, unobserved properties or playback. Private native evidence, music and review records remain excluded.

## Earlier native development evidence

Development native testing on macOS with Sibelius 2025.12.1 completed on October 20, 2026. The private evidence contains copyrighted scores and is not distributed.

- All 14 synthetic controller tests passed.
- Full-size native reading passed on a 23-staff, 478-bar score with 61,387 objects.
- Disposable 32-bar extracts retaining all staves from two different band scores passed individual and grouped PDF exports, grouped-part creation, duplicate-part selection, pitch/spelling and chord-head edits, articulation, text, lines, symbols, ties, percussion notehead and tremolo changes.
- Grace/rest, 4:6 tuplet and two-head brass-chord voice rebuilding passed full observed-score comparisons and PDF exports.
- Duplicate request/stale baseline guards and exact observed-fact recovery passed. Original production file hashes were unchanged.
- Rendered smoke checks confirmed visible grace, tuplet and chord output. The extracts had existing/trimmed-heading overlaps; these tests were not publication engraving certification or a full musical source audit.

The public source package removes the private fixture helper and project-specific paths. Its synthetic tests and installer generation are checked separately; this packaging is not a native acceptance run on every supported-looking API combination or Sibelius version. Nested tuplets, optional APIs, full playback fidelity, and Windows remain unverified or excluded as described in the README.

Musical scope is brass-band instruments and percussion. Tests establish ordinary multi-note chord support, not chord symbols/diagrams. Lyrics, vocal underlay, bowing/fingering, string harmonics, tablature and other specialist notation were not validated and are not promised to survive a complete-voice rebuild.

Enabled line playback is verified against Sibelius’s eight supported repeat passes. The retained ninth diagnostic query must be false; regression coverage rejects a wrong supported pass or unexpected diagnostic value. This corrected a host-side false rejection without rerunning the native edit.
