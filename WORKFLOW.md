# Reviewing a complete set of parts

Use the published individual parts as the musical reference. Native snapshots locate edit targets and check preservation; they do not establish source accuracy. The bridge is developed for brass-band instruments and percussion. Ordinary chords are supported; lyrics, chord symbols and string-specific notation are outside the validated scope.

## Agree on completion first

List the requested parts, any already-approved parts to preserve, and what the review must establish. For a musical review, check written pitches and accidentals, rhythms/rests/tuplets, ties/slurs/articulations, dynamics/hairpins, tempo and instrument/playing instructions. Fix layout when it obscures musical meaning. Exact bar widths, page matching and decorative engraving are separate work unless requested.

Keep one score writer. Reviewers can prepare source findings while native work runs, but must not change the active score. A sequential part reader can accumulate corrections across the score; finishing every native edit before beginning the next source part is unnecessarily slow. Use the established reader/model when it is working; repeat model comparisons or pilots only to resolve a specific new uncertainty.

## Read once, batch repairs, prove the differences

1. Save a review copy and record source/score hashes. Discover once. Resolve the part catalog, including grouped and duplicate parts, before reviewing. Export the requested set with `export-set`, sharing one full inventory. Include approved parts in preservation checks when global changes can affect them.
2. Review each source part sequentially by matching bar numbers, with notes and expression together. Record exact bar/voice/position, source evidence, observed discrepancy, confidence and correction intent. Enlarge ambiguous source glyphs and compare nearby examples. Do not infer missing music from an importer, inventory or alternate renderer alone.
3. Prepare all confirmed corrections offline. Compile scalar operations against exact targets. Batch independent `REPLACE_VOICE` repairs by distinct staff/bar; put two voices of the same bar in separate waves. Keep rebuild batches separate from scalar batches. Preserve actual tuplets, instruments, grace counts and finite voice timing; do not insert convenient filler rests to conceal an incorrect recipe.
4. Apply each coherent wave with one native recovery copy and one full before/after comparison. Use the successful apply job as the next baseline. Avoid redundant discovery and native preview for established operations: apply already preflights targets. New or uncertain capabilities need a disposable fixture before touching a working score.
5. Use `export-proof` for repeated PDF-only output after a guarded wave. Export affected parts together, plus protected parts when shared changes could affect them. Inspect corrected bars and neighbors. Compare rendered pages with their previously accepted versions; carry forward prior proof only for pages that match at the recorded resolution. Changed pages need visual inspection. Keep the original complete source coverage and link each successive proof to its exact PDF hash.
6. Make only necessary readability repairs. Re-export and inspect their actual effect. Native UI/accessibility readback alone is insufficient. A full-score graphical change can leave a dynamic-part override unchanged; inspect the intended part. If changes were made outside the bridge, establish the required native preservation comparison separately before promotion. A PDF-only export never establishes that preservation.
7. Promote the accepted native file and PDFs together, preserving the previous production file. Verify destination hashes. Record the accepted source proofs, native guard, protected-part evidence, any unresolved findings and the final paths. Historical failed/interim reports remain historical; name the superseding proof explicitly so an old residual list is not mistaken for current work.

```sh
./score-bridge discover --run
./score-bridge export-set --baseline DISCOVERY_JOB --part '1;2,3;4' --run
./score-bridge apply --baseline GUARDED_JOB --operations corrections.json --run
./score-bridge export-proof --baseline APPLY_JOB --part '1;2,3;4' --run
```

Substitute real job IDs and freshly inspected targets. `export-proof` checks the score identity and requested PDFs, not the current musical snapshot, and cannot become an edit baseline. A source PDF comparison and a successful observed-property guard answer different questions; both are needed for a corrected score.

## Avoid the slow and unreliable paths

- **Budget by native waves, not instruments.** Large observed inventories have taken roughly 4 minutes for a 22-staff/430-bar score and 6–7 minutes for a 23-staff/478-bar score. An edit needs two inventories. Fixture timings do not predict full-score latency. Independent batching saves repeated scans; skipping unrelated-change checks would sacrifice the guard.
- **Separate output from validation.** Repeated PDF export through a path that also rescans the score can cost minutes unnecessarily. Fast native UI all-part exports took about 5 seconds in development; `export-proof` provides a bridge route with explicitly narrower evidence; a full-size 20-part/231-page run took about 19.4 seconds. Do not advertise a universal timing or use a PDF success flag to authorize edits.
- **Wait for the original request.** A caller timeout is not native cancellation. Use `status` and `collect`, inspect the live daemon and original job, and recover from the original backup after a real failed mutation. Never submit the same edit again just because a wait expired. The default running-command wait is 1,800 seconds and is configurable.
- **Switch parts through the bridge.** `show-part --score /absolute/path/example.sib --part 1,2` verifies the exact score and unique part. Avoid repeated tab-picker automation. Opening an already-open file may not activate its window; use the application's window switcher when necessary.
- **Treat native UI controls as fallible.** Some Qt accessibility setters reported changed values without committing the native action. Physical controls in a floating Inspector worked more reliably in development. Verify exact selected-object counts, actual field units and the exported result. A text filter may select several matching captions and change them all. An apparent search focus does not prove keystrokes will reach the search field; do not send navigation arrows or Space speculatively to a score.
- **Distinguish visibility from musical data.** Hidden rests may still generate automatic printed rest ink. Do not delete timed notes/rests or change bar durations merely to remove an unwanted glyph. Source-proven free/unmeasured passages may need a clear equivalent representation, with exact event preservation and printed proof.
- **Do not relax stale-baseline checks.** Reopening can normalize inline text formatting. Inspect the exact fresh delta and establish an audited baseline rather than ignoring all formatting or automatically retrying. Derived grace offsets can change while later events are added; restore them after the complete voice is stable, as the rebuild implementation now does.
- **Stop failed experiments early.** A setter can return without taking effect. Unsupported optional properties and external-plugin calls can fail at runtime even when syntax checks pass. Keep unvalidated structural/resize commands out of a review session, recover after a failed mutation, and log a narrowly scoped future fix. Test new code on disposable scores, not valuable working files.
- **Keep environment issues separate.** An idle-screen password policy differs from display sleep. Do not weaken managed security settings to keep automation running. Prefer native bridge operations that do not depend on screen focus; arrange user attention only for a genuine modal alert or required visible action.

## Follow-up engineering priorities

1. Profile native snapshot getters and serialization with synthetic and full-size fixtures. Any optimization must return the same complete facts and preserve stale-baseline, multiplicity and unrelated-change detection. No scanner speedup is claimed by this release.
2. Add narrowly tested adapters for recurring supported notation that currently needs native UI. Each needs exact target preconditions, native readback, recovery and printed acceptance; generic arbitrary-command execution is not a substitute.
3. Investigate stable formatting serialization, automatic-rest display and supported bar-duration repairs independently. Do not globally normalize snapshots, reuse withdrawn resize code, or silently change rhythm to make a guard pass.
4. Automate a review queue that joins source coverage, corrective waves, PDF hashes, changed-page proof and promotion receipts. It should distinguish coverage, observed native consistency and visual musical acceptance rather than combining them into one green status.

Playback audition, specialist notation outside the brass/percussion scope, and exact publication engraving require their own validation. A comprehensive visual review reduces errors; it cannot guarantee none remain.
