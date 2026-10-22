# Editing operations

Designed and tested for brass-band/percussion work. Ordinary notehead chords are supported; chord symbols/diagrams, lyrics, string-specific notation and other specialist attachments are outside the validated scope. See the musical-scope table in the README before rebuilding a voice.

Every request identifies the exact active score filename, title, staff count, bar count, and transposing-score state. Edits additionally compare the entire observed full-score snapshot with their baseline. Object edits include their exact pre-edit facts. One operation per existing object per request prevents invalidated references from being reused after pitch changes; voice rebuilds can share a rhythm-only batch of distinct staff/bar targets. All targets are preflighted before mutation. Musical edits take place in full-score context, and the previous dynamic-part context is restored on normal exits. Graphical edits in score context may affect parts too. The bridge supports a narrowly guarded part context for graphical overrides; see below.

Supported operation kinds:

| Operation | Purpose |
| --- | --- |
| `PITCH` | One chord note's written pitch and spelling, including downward chromatic changes |
| `NOTE_SET` | Outgoing ties/tie style, notehead style, accidental display, hidden/bracketed noteheads |
| `ARTICULATION` | Set/clear a specified native articulation |
| `SET` | Existing text/style, line duration/end offsets, graphical offsets/visibility/cue size, Magnetic Layout, tremolos, beams, rest position, symbol size, tuplet bracket/style/full-duration appearance |
| `ADD_TEXT` | Staff expression/technique text or system text using a native style ID |
| `ADD_LINE` | Slurs, hairpins, trills and other native staff lines, with explicit playback policy (default off) |
| `ADD_SYMBOL` | Native symbol and size at an exact position |
| `DELETE` | Existing staff/system text, lines, and symbols; never bars, clefs, or notes through this command |
| `REPLACE_VOICE` | Explicit complete-bar voice recipe for rhythm, rests, chords, tuplets/nested tuplets, and grace notes |

Each operation has `id`, `op`, `staff`, and `bar`. Existing targets also require the `ordinal` returned by the inventory. `PITCH` takes `note` (zero-based within the chord), `written_pitch` (MIDI number), and `written_diatonic` (middle C = 35). `SET`/`NOTE_SET` take `property` and `value`; `ARTICULATION` uses the native articulation number as `property` and a Boolean `value`. Additions take `position` in Sibelius units (256 per quarter), native `style` or `symbol`, and their content/duration. Voice numbers are 1–4; 0 means all voices where the native object supports it. Booleans must be JSON true/false, not strings. Matching additions already present in the baseline are refused, preventing duplication across newly prepared requests too.

`recipe JOB --staff N --bar N --voice N` extracts an explicit recipe where the native timing is already coherent. Edit it only against the source PDF. A recipe names all tuplets, parent-relative positions, and every event's intended native facts. The controller uses exact rational arithmetic to reject gaps, overlaps and bar overflow before a rebuild. Notes are added through their actual tuplet containers. A bar with shared-voice slurs is refused; ordinary voice-specific slurs are restored and compared, while other voices and non-note objects must remain unchanged. Malformed existing timing may require constructing a source-correct recipe rather than extracting the malformed one unchanged.

## Dynamic-part graphical overrides

Use `show JOB --context part` to inspect part-relative addresses. `preview` and `apply --part SIGNATURE` require a verified export/part-edit baseline for that exact signature. Only `SET` of `Dx`, `Dy`, `RhDx`, `RhDy`, `Hidden`, and `Magnetic` is allowed. The full-score and part baselines are both checked before editing. Verification requires an unchanged observed full score plus exactly the declared part changes. Review the affected PDF and re-export protected parts to establish layout preservation beyond the observed fields. Context snapshots are retained as `expected-context.tsv`, `context-before.tsv`, and `context-after.tsv`.

## Music-text dynamics

For new expression dynamics, add `"music_text": true` to an `ADD_TEXT` operation. Only dynamic glyph letters are accepted. For existing dynamics, a `SET Text` operation may use the controller's `music_dynamic()` formatted value. Verification checks plain text and exact native music-text formatting. Use ordinary expression text for word instructions.

## Independent rhythm batches

A request can contain multiple `REPLACE_VOICE` operations only when every `(staff, bar)` pair differs. Two voices in the same staff/bar need separate waves because rebuilding invalidates native handles. Mixing scalar edits with rebuilds is refused. All recipes/targets are validated before any mutation; the batch shares one recovery file and one complete observed-score before/after comparison. Every recipe is separately hashed. The rebuilt voice's grace offsets are restored and read back after all events, beams and slurs have settled.

Use the successful apply job as the next baseline; do not repeat discovery between unchanged bridge operations. A failed guard is never permission to ignore offsets, stems, font changes or other fields: inspect the exact delta, recover when required, and establish a valid fresh baseline.

## Bold Roman instructions

For a `SET Text` value, `bold_roman("Instruction")` returns the supported inline formatting. Exact plain text and formatting are verified. Sibelius may normalize formatting serialization when reopening a file; the stale-baseline check still applies. Do not globally strip formatting fields or allow arbitrary mismatches.

## Proof exports

`export-proof` is strictly a read-only PDF-output action with no operations or snapshots. All part selectors are resolved before exporting. It returns `PDF_PROOF_EXPORTED`, then host PDF checks produce an explicitly non-baseline result. The normal `apply`, `preview`, `ensure-part`, `inspect` and snapshot-export paths require a verified native baseline and refuse proof-only jobs.
