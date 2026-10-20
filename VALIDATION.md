# Validation status

Development native testing on macOS with Sibelius 2025.12.1 completed on October 20, 2026. The private evidence contains copyrighted scores and is not distributed.

- All 13 synthetic controller tests passed.
- Full-size native reading passed on a 23-staff, 478-bar score with 61,387 objects.
- Disposable 32-bar extracts retaining all staves from two different band scores passed individual and grouped PDF exports, grouped-part creation, duplicate-part selection, pitch/spelling and chord-head edits, articulation, text, lines, symbols, ties, percussion notehead and tremolo changes.
- Grace/rest, 4:6 tuplet and two-head brass-chord voice rebuilding passed full observed-score comparisons and PDF exports.
- Duplicate request/stale baseline guards and exact observed-fact recovery passed. Original production file hashes were unchanged.
- Rendered smoke checks confirmed visible grace, tuplet and chord output. The extracts had existing/trimmed-heading overlaps; these tests were not publication engraving certification or a full musical source audit.

The public source package removes the private fixture helper and project-specific paths. Its synthetic tests and installer generation are checked separately; this packaging is not a native acceptance run on every supported-looking API combination or Sibelius version. Nested tuplets, optional APIs, full playback fidelity, and Windows remain unverified or excluded as described in the README.

Musical scope is brass-band instruments and percussion. Tests establish ordinary multi-note chord support, not chord symbols/diagrams. Lyrics, vocal underlay, bowing/fingering, string harmonics, tablature and other specialist notation were not validated and are not promised to survive a complete-voice rebuild.
