# Sibelius Score Bridge

A local bridge for inspecting, exporting and editing native Sibelius scores from an AI coding assistant or a terminal. It combines a ManuScript plugin with a Python controller and a Node.js connection to Sibelius Connect. Musical edits use Sibelius's native objects; no mouse automation or MusicXML round-trip is required.

Independent experimental software. Not affiliated with, endorsed by, or supported by Avid or OpenAI. A separately licensed installation of Sibelius is required. This is a source-code release, not an official directory or marketplace listing. See [Avid and licensing](LEGAL.md).

## What it does

- Discover the active score, staff identities, bars, dynamic parts and native notation objects.
- Export an individual or grouped dynamic part to PDF, with explicit selection when parts have duplicate staff membership.
- Preview and apply guarded pitch/spelling, chord-head, articulation, tie, text, line, symbol, percussion notehead and selected engraving edits.
- Rebuild one complete bar/voice from an explicit recipe containing notes, rests, chords, tuplets and grace notes.
- Save separate native recovery and candidate files; compare all observed score objects with the expected changes.

The bridge does not contain a model or automatically judge musical correctness. An assistant must compare the exported PDF with an authorized reference, establish the intended correction, use exact native targets, and review the corrected PDF. Codex is one possible client; the command-line interface is not tied to one model provider.

## Musical scope

Developed for **brass-band instruments and percussion**, and validated on that repertoire. General note/rest/chord, text, articulation, line and symbol primitives may be useful elsewhere, but this is not a general-purpose editor for every Sibelius notation feature.

| Area | Status |
| --- | --- |
| Brass-band notes, rests, transposing written pitches, dynamics and common articulations | Targeted and tested |
| Percussion noteheads and the tested tremolo/notation operations | Targeted and tested; not a complete percussion-map editor |
| Ordinary chords (multiple simultaneous noteheads) | Supported; chord-head editing and two-head brass-chord rebuilding tested |
| Chord symbols such as Cmaj7, guitar chord diagrams | No dedicated support or validation |
| Lyrics and vocal underlay | No dedicated support or validation |
| Strings, bowing/fingering, harmonics, tablature, guitar techniques, pedal/harp notation | Outside the tested scope; no preservation guarantee |
| Nested tuplet combinations, specialized engraving and live playback | Limited or unverified; see validation notes |

A generic symbol or text command is not semantic support for specialist notation. Unsupported properties may be absent from the inventory and may be lost during complete-voice rebuilding. Use disposable copies and source-specific validation before working outside the tested brass/percussion scope. In particular, do not treat the voice-rebuild operation as safe for lyrics, tablature, string-specific properties or other unobserved attachments.

## Requirements

- macOS and a licensed Sibelius installation supporting ManuScript and Sibelius Connect. The native development build was tested with Sibelius 2025.12.1 on macOS; other versions and Windows are unverified.
- Python 3.11 or newer and `pypdf` for PDF validation.
- Node.js with the built-in global `WebSocket` API (Node 22 or newer).

Sibelius and its bundled `utils` plugin are runtime dependencies; neither is distributed here.

## Install

```sh
git clone https://github.com/shaevitz/sibelius-score-bridge.git
cd sibelius-score-bridge
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./score-bridge install
```

The installer generates `ScoreBridge.plg` in your user's `Library/Application Support/Avid/Sibelius/Plugins/Codex/` folder. Previous installed copies are retained in `install-history/`. Restart Sibelius after installation. Reinstall after moving the checkout: the generated plugin embeds its local runtime path. Do not commit generated plugins or share them as portable binaries.

In Sibelius, enable **Preferences > Input Devices > Allow Sibelius to be remotely controlled by other applications**. Then start:

```sh
./score-bridge start
```

Leave that process running and accept the local Codex Score Bridge connection in Sibelius. The daemon connects only to `127.0.0.1:1898`; the bridge itself sends nothing to a model provider or external server. An AI assistant's own data-handling rules still apply to any score content supplied to it.

## Inspect and export

Open the intended score in Sibelius, or use an absolute filename:

```sh
./score-bridge open /absolute/path/example.sib
./score-bridge doctor
./score-bridge discover --run
./score-bridge show JOB --staff 1 --bars 1:8
./score-bridge export --baseline JOB --part 1 --run
```

`JOB` is the job ID or absolute directory returned by the preceding command. Each job has its own directory under `runtime/jobs/`. Exported `part.pdf` is checked for readability, page count and hash. `before.tsv` describes the full score; `context.tsv` describes the exported part using part-relative staff numbers.

Use `--part 1,2` for a matching grouped part or `score` for the full score. Missing or ambiguous parts are refused. Use a fresh `parts.tsv` catalog and `--part '8#10'` to explicitly select the part at catalog index 10 containing full-score staff 8. The index can change after parts are created or reordered. To create a missing grouped part:

```sh
./score-bridge ensure-part --baseline JOB --part 1,2 --name 'Combined part' --run
```

This saves native backup/candidate files and verifies unchanged observed full-score content. An existing unique matching part is left unchanged.

## Guarded editing

Prepare a JSON operation array using the exact staff, bar and ordinal reported by `show`. For example, after inspecting the actual object:

```json
[
  {"id":"fix_pitch","op":"PITCH","staff":1,"bar":3,"ordinal":2,
   "note":0,"written_pitch":66,"written_diatonic":38}
]
```

This is a format example, not a correction to run blindly. Written pitch uses MIDI numbers; written diatonic pitch uses middle C = 35. The note index is zero-based within the chord.

```sh
./score-bridge preview --baseline JOB --operations edits.json --run
./score-bridge apply --baseline JOB --operations edits.json --run
```

Use the same unmodified baseline for preview and apply. Apply compares the entire observed native score with that baseline, checks every target before mutation, writes `before.sib`, makes the edits, writes `candidate.sib`, and verifies the full observed result. The original file is not automatically overwritten. One operation per existing object is allowed per request; complete-voice rebuilding runs alone. Re-export and visually verify a candidate before making it your working score.

Operation details are in [OPERATIONS.md](OPERATIONS.md).

## Recovery

Never blindly retry an edit after failure, timeout or disconnection. Retain the job, inspect `status.tsv`, reconnect if necessary and use:

```sh
./score-bridge collect JOB
./score-bridge recover JOB
```

Recovery requires the active score to match the failed request's original filename. It closes that unsaved score without saving it and opens the job's native recovery copy. The controller waits for the backup to become active and checks title/bar count. Discover again afterward because the backup has a different filename. A job with a backup cannot be abandoned. A read-only failure without a backup can be resolved with `abandon JOB --reason 'explanation'`.

Native exceptions are not atomic. A native status such as `APPLIED_UNVERIFIED` alone is not success; use the host's `verified.json` result. Observed-property comparison cannot certify every hidden engraving or playback property.

## Validation and limits

Run the synthetic controller tests without Sibelius:

```sh
.venv/bin/python -m unittest discover -p 'test_*.py' -v
```

[VALIDATION.md](VALIDATION.md) summarizes native development testing. Private score files, PDFs, inventories, logs and score-specific acceptance scripts are intentionally excluded from this release. No copyrighted music examples or Avid manuals are included. There are no hardcoded personal home paths, score titles, model preferences, credentials or private review logs. The author attribution and GitHub repository address identify the project owner; they are not runtime configuration.

Optional L.V./incoming-tie API getters are unavailable in the tested Sibelius build, so their corresponding edits are excluded. Nested tuplets are implemented but nested combinations need a disposable validation case before use. General instrument replacement, score restructuring, lyrics and arbitrary native code execution are not exposed. Graphical edits run in full-score context; part-only isolation is not claimed. Voice rebuilding does not certify full MIDI/live-playback fidelity.

## License

Original project source is available under the [MIT License](LICENSE). This does not license Sibelius, Avid documentation, bundled dependencies, trademarks, or any music processed with the tool.
