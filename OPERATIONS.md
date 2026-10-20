# Editing operations

Designed and tested for brass-band/percussion work. Ordinary notehead chords are supported; chord symbols/diagrams, lyrics, string-specific notation and other specialist attachments are outside the validated scope. See the musical-scope table in the README before rebuilding a voice.

Every request identifies the exact active score filename, title, staff count, bar count, and transposing-score state. Edits additionally compare the entire observed full-score snapshot with their baseline. Object edits include their exact pre-edit facts. One operation per existing object per request prevents invalidated references from being reused after pitch changes; complete-voice rebuilds run alone. All targets are preflighted before mutation. Musical edits take place in full-score context, and the previous dynamic-part context is restored on normal exits. Graphical edits therefore may affect parts as well as the full score; no part-only isolation is claimed.

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
