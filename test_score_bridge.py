import copy
import json
import subprocess
import sys
from unittest.mock import patch
import tempfile
from pathlib import Path
import unittest

import score_bridge as bridge
from rhythm import validate_recipe


def fixture():
    note = dict(Type='NoteRest', Position='0', VoiceNumber='1', Voices='1',
                Hidden='false', CueSize='false', Dx='0', Dy='0', Magnetic='true',
                Played=','.join(['true'] * 9), Duration='256', Grace='false',
                Slash='false', SingleTremolos='0', DoubleTremolos='0', Beam='0',
                Stemweight='-2', RestPosition='0', Articulations=','.join(['false'] * 16),
                NoteCount='1', Notes='58,34,60,35,false,Solid,0,0,False,False,False,false,Solid')
    return {'score': ['SCORE', 'Example', '/scores/example.sib', '2', '1', 'true'],
            'staves': {1: ['Trumpet', 'instrument.brass.trumpet']},
            'bars': {(1, 1): ['1', '1024', '7', '0', '0', 'instrument.brass.trumpet', '-2', '-1']},
            'objects': {(1, 1, 0): note}}


class BridgeTests(unittest.TestCase):
    def test_installation_through_symlink_has_identical_native_build(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            alias = root/'checkout-alias'
            alias.symlink_to(bridge.ROOT, target_is_directory=True)
            one, two = root/'one.plg', root/'two.plg'
            for script, output in ((bridge.ROOT/'score_bridge.py', one), (alias/'score_bridge.py', two)):
                result = subprocess.run([sys.executable, str(script), 'install', '--destination', str(output)],
                                        check=True, text=True, capture_output=True)
                self.assertEqual(json.loads(result.stdout)['version'], bridge.VERSION)
            self.assertEqual(one.read_bytes(), two.read_bytes())

    def test_bold_roman_requires_exact_plain_text_and_formatting(self):
        before=fixture()
        before['objects'][(1,1,0)]=dict(Type='Text',Position='0',VoiceNumber='0',Text='Wild!',StyleId='text.staff.technique',Formatting='Wild!')
        op=dict(id='bold',op='SET',staff=1,bar=1,ordinal=0,property='Text',value=bridge.bold_roman('Wild!'))
        row=bridge.compile_operation(op,before)
        after=copy.deepcopy(before); after['objects'][(1,1,0)]=bridge.expected_target(before['objects'][(1,1,0)],row)
        self.assertEqual(after['objects'][(1,1,0)]['Text'],'Wild!')
        self.assertFalse(bridge.verify_changes(before,after,[row]))
        after['objects'][(1,1,0)]['Formatting']='Wild!'
        self.assertTrue(bridge.verify_changes(before,after,[row]))
        for text in ('','x\\B\\','x\n'):
            with self.assertRaises(ValueError): bridge.bold_roman(text)

    def test_export_set_selectors_are_unique_and_path_safe(self):
        self.assertEqual(bridge.export_signatures('2,3;8,9,10,11;4#7'), ['2,3','8,9,10,11','4#7'])
        for value in ('', '1;1', '../file', '1;/tmp/file', '0', ';1', '1;', '1\n2', ';'.join(map(str,range(1,34)))):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.export_signatures(value)

    def test_export_set_invalid_selector_creates_no_job(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            source = Path(d) / 'baseline'; source.mkdir()
            (source/'manifest.json').write_text('{}')
            (source/'verified.json').write_text(json.dumps({'ok': True, 'action': 'DISCOVER'}))
            bridge.write_rows(source/'before.tsv', [fixture()['score']])
            with self.assertRaises(ValueError):
                bridge.submit('EXPORT_SET', str(source), '1;../../other')
            self.assertFalse((Path(d)/'jobs').exists())
            self.assertFalse((Path(d)/'pending.txt').exists())

    def test_export_set_requires_every_pdf_and_unchanged_full_facts(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            source = self.part_baseline(Path(d))
            result = bridge.submit('EXPORT_SET', str(source), '1;2')
            job = Path(result['job'])
            (job/'before.tsv').write_bytes((source/'before.tsv').read_bytes())
            bridge.write_rows(job/'parts.tsv', [['0','true','Full Score','1,2'],['1','false','Part1','1'],['2','false','Part2','2']])
            bridge.write_rows(job/'status.tsv', [['EXPORTED_UNVERIFIED']])
            from pypdf import PdfWriter
            def blank(name):
                writer = PdfWriter(); writer.add_blank_page(width=200, height=200)
                with (job/name).open('wb') as stream: writer.write(stream)
            blank('part-1.pdf')
            self.assertFalse(bridge.collect(job)['ok'])
            blank('part-2.pdf')
            passed = bridge.collect(job)
            self.assertTrue(passed['ok'])
            self.assertEqual(set(passed['pdfs']), {'1','2'})
            rows = bridge.read_rows(job/'before.tsv')
            rows[-1][-1] = rows[-1][-1].replace('Dy=0', 'Dy=64')
            bridge.write_rows(job/'before.tsv', rows)
            self.assertFalse(bridge.collect(job)['ok'])

    def proof_fixture(self, root):
        from pypdf import PdfWriter
        source = self.part_baseline(root)
        result = bridge.submit('EXPORT_PROOF', str(source), '1;2')
        job = Path(result['job'])
        header = bridge.read_rows(job/'request.tsv')[0]
        bridge.write_rows(job/'identity.tsv', [['SCORE', *header[3:8]]])
        bridge.write_rows(job/'status.tsv', [['PDF_PROOF_EXPORTED']])
        for signature in ('1', '2'):
            writer = PdfWriter(); writer.add_blank_page(width=200, height=200)
            with (job/f'part-{signature}.pdf').open('wb') as stream:
                writer.write(stream)
        return job

    def test_proof_exports_validate_pdfs_without_claiming_native_verification(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            job = self.proof_fixture(Path(d))
            self.assertFalse((job/'before.tsv').exists())
            result = bridge.collect(job)
            self.assertTrue(result['ok'])
            self.assertFalse(result['baseline_usable'])
            self.assertFalse(result['musical_state_verified'])
            self.assertTrue(result['requires_visual_review'])
            self.assertEqual(set(result['pdfs']), {'1', '2'})
            self.assertEqual(result['pdfs']['1']['pages'], 1)
            # Even a caller supplying a snapshot cannot turn proof success into
            # authorization for a mutation, inspection baseline or part creation.
            bridge.write_rows(job/'before.tsv', [fixture()['score']])
            for action in ('APPLY', 'PREVIEW', 'INSPECT', 'ENSURE_PART', 'EXPORT_PROOF'):
                with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'not native edit baselines'):
                    bridge.submit(action, str(job), '1')

    def test_proof_exports_reject_missing_corrupt_pdfs_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            job = self.proof_fixture(Path(d))
            pdf = job/'part-2.pdf'; original = pdf.read_bytes()
            pdf.unlink()
            self.assertFalse(bridge.collect(job)['ok'])
            pdf.write_bytes(b'not a PDF')
            self.assertFalse(bridge.collect(job)['ok'])
            pdf.write_bytes(original)
            rows = bridge.read_rows(job/'identity.tsv'); rows[0][2] = '/tmp/different.sib'
            bridge.write_rows(job/'identity.tsv', rows)
            self.assertFalse(bridge.collect(job)['ok'])

    def test_local_status_never_invokes_sibelius_and_checks_daemon_liveness(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)), patch.object(bridge, 'invoke', side_effect=AssertionError('must not invoke')):
            root = Path(d)
            (root/'connection.json').write_text(json.dumps({'status':'running', 'pid':12345}))
            with patch.object(bridge.os, 'kill'):
                self.assertTrue(bridge.job_status()['daemon_process_alive'])
            with patch.object(bridge.os, 'kill', side_effect=ProcessLookupError):
                self.assertFalse(bridge.job_status()['daemon_process_alive'])

    def test_timeout_keeps_original_invocation_and_never_retries(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            root = Path(d)
            (root/'connection.json').write_text(json.dumps({'status':'ready', 'pid':12345}))
            with patch.object(bridge.os, 'kill'), patch.object(bridge.time, 'monotonic', side_effect=[0, 2]):
                with self.assertRaisesRegex(ValueError, 'do not submit or invoke it again'):
                    bridge.invoke('ScoreStatus', timeout=1)
            self.assertEqual(json.loads((root/'invoke.json').read_text())['method'], 'ScoreStatus')
            self.assertFalse((root/'pending.txt').exists())
        for value in ('0', '-1', 'nan', 'inf'):
            with self.subTest(value=value), self.assertRaises(bridge.argparse.ArgumentTypeError):
                bridge.positive_seconds(value)

    def test_nested_encoding_preserves_formatting_and_separators(self):
        value = '♭|%0A\n\\B\\ff\\b\\\r'
        self.assertEqual(bridge.dec(bridge.enc(value)), value)
        fields = {'Type': 'Text', 'Text': value}
        self.assertEqual(bridge.fact(bridge.fact_text(fields)), fields)

    def test_native_unicode_protocol_roundtrip(self):
        rows = [['one', '', '♭|%\n'], ['two', 'false']]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'request.tsv'
            bridge.write_rows(p, rows)
            self.assertEqual(bridge.read_rows(p), rows)

    def test_detects_change_to_an_unrelated_note_property(self):
        before = fixture(); after = copy.deepcopy(before)
        op = bridge.compile_operation(dict(id='pitch', op='PITCH', staff=1, bar=1,
                                          ordinal=0, written_pitch=62, written_diatonic=36), before)
        after['objects'][(1, 1, 0)] = bridge.expected_target(before['objects'][(1, 1, 0)], op)
        after['objects'][(1, 1, 0)]['Stemweight'] = '0'
        self.assertFalse(bridge.verify_changes(before, after, [op]))
        after['objects'][(1, 1, 0)]['Duration'] = '128'
        self.assertTrue(bridge.verify_changes(before, after, [op]))

    def test_detects_instrument_change_during_pitch_edit(self):
        before = fixture(); after = copy.deepcopy(before)
        after['bars'][(1, 1)][5] = 'instrument.brass.tuba'
        self.assertTrue(bridge.verify_changes(before, after, []))

    def test_detects_added_duplicate(self):
        before = fixture(); after = copy.deepcopy(before)
        after['objects'][(1, 1, 1)] = dict(after['objects'][(1, 1, 0)])
        self.assertTrue(bridge.verify_changes(before, after, []))

    def test_rejects_invalid_numeric_and_boolean_properties(self):
        for prop, value in [('Hidden', 'true'), ('SingleTremolos', 99), ('Duration', -1)]:
            with self.subTest(prop=prop), self.assertRaises(ValueError):
                bridge.compile_operation(dict(id='bad', op='SET', staff=1, bar=1,
                                              ordinal=0, property=prop, value=value), fixture())

    def test_cannot_delete_notes_or_structural_objects(self):
        with self.assertRaises(ValueError):
            bridge.compile_operation(dict(id='bad', op='DELETE', staff=1, bar=1, ordinal=0), fixture())

    def test_rest_and_tremolo_setters_require_matching_objects(self):
        with self.assertRaises(ValueError):
            bridge.compile_operation(dict(id='bad', op='SET', staff=1, bar=1,
                                          ordinal=0, property='RestPosition', value=1), fixture())
        rest = fixture()
        rest['objects'][(1, 1, 0)].update(NoteCount='0', Notes='')
        for prop in ('SingleTremolos', 'DoubleTremolos'):
            with self.subTest(prop=prop), self.assertRaises(ValueError):
                bridge.compile_operation(dict(id='bad', op='SET', staff=1, bar=1,
                                              ordinal=0, property=prop, value=1), rest)

    def test_pitch_spelling_and_octave_intervals(self):
        self.assertEqual(bridge.transpose_interval(60, 35, 62, 36), (1, 5))
        self.assertEqual(bridge.transpose_interval(60, 35, 63, 37), (2, 4))
        self.assertEqual(bridge.transpose_interval(60, 35, 72, 42), (7, 5))
        self.assertEqual(bridge.transpose_interval(60, 35, 57, 33), (-2, 4))

    def test_mutations_require_exact_ordinal(self):
        with self.assertRaises(ValueError):
            bridge.compile_operation(dict(id='bad', op='PITCH', staff=1, bar=1,
                                          ordinal=50, written_pitch=62, written_diatonic=36), fixture())

    def test_text_add_requires_correct_attachment(self):
        with self.assertRaises(ValueError):
            bridge.compile_operation(dict(id='bad', op='ADD_TEXT', staff=1, bar=1,
                                          position=0, style='text.system.tempo', text='test'), fixture())

    def test_added_line_checks_eight_supported_playback_passes(self):
        for playback in (False, True):
            with self.subTest(playback=playback):
                before = fixture()
                row = bridge.compile_operation(dict(id='line', op='ADD_LINE', staff=1, bar=1,
                    position=0, duration=256, voice=1, style='line.staff.hairpin.crescendo',
                    playback=playback), before)
                after = copy.deepcopy(before)
                after['objects'][(1, 1, 1)] = dict(Type='CrescendoLine', Position='0',
                    StyleId='line.staff.hairpin.crescendo', Duration='256', VoiceNumber='1',
                    Played=','.join([str(playback).lower()] * 8 + ['false']))
                self.assertFalse(bridge.verify_changes(before, after, [row]))
                # A wrong supported pass must still fail verification.
                after['objects'][(1, 1, 1)]['Played'] = ','.join(
                    [str(playback).lower()] * 7 + [str(not playback).lower(), 'false'])
                self.assertTrue(bridge.verify_changes(before, after, [row]))
                # Do not silently ignore unexpected out-of-range data either.
                after['objects'][(1, 1, 1)]['Played'] = ','.join(
                    [str(playback).lower()] * 8 + ['true'])
                self.assertTrue(bridge.verify_changes(before, after, [row]))

    def test_formatted_dynamic_set_keeps_plain_text_and_checks_font(self):
        before = fixture()
        before['objects'][(1, 1, 1)] = dict(Type='Text', Position='0', VoiceNumber='0',
            Text='ffp', StyleId='text.staff.expression', Formatting='ffp')
        row = bridge.compile_operation(dict(id='format', op='SET', staff=1, bar=1,
            ordinal=1, property='Text', value=bridge.music_dynamic('ffp')), before)
        after = copy.deepcopy(before)
        after['objects'][(1, 1, 1)]['Formatting'] = bridge.music_dynamic('ffp')
        self.assertFalse(bridge.verify_changes(before, after, [row]))
        after['objects'][(1, 1, 1)]['Formatting'] = 'ffp'
        self.assertTrue(bridge.verify_changes(before, after, [row]))

    def test_music_text_addition_requires_dynamic_content_and_exact_format(self):
        before = fixture()
        op = dict(id='dynamic', op='ADD_TEXT', staff=1, bar=1, position=0,
            voice=0, style='text.staff.expression', text='ffz', music_text=True)
        row = bridge.compile_operation(op, before)
        after = copy.deepcopy(before)
        after['objects'][(1, 1, 1)] = dict(Type='Text', Position='0', VoiceNumber='0',
            Text='ffz', StyleId='text.staff.expression', Formatting=bridge.music_dynamic('ffz'))
        self.assertFalse(bridge.verify_changes(before, after, [row]))
        after['objects'][(1, 1, 1)]['Text'] = 'fz'
        self.assertTrue(bridge.verify_changes(before, after, [row]))
        for change in ({'text': 'poco cresc.'}, {'style': 'text.staff.technique'}, {'music_text': 'true'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                bridge.compile_operation(dict(op, **change), before)

    def part_baseline(self, root):
        baseline = root / 'jobs' / 'baseline'
        baseline.mkdir(parents=True)
        full = fixture()
        context = copy.deepcopy(full)
        context['objects'][(1, 1, 0)]['Dy'] = '64'
        for name, snap in [('before.tsv', full), ('context.tsv', context)]:
            rows = [snap['score']]
            rows += [['STAFF', k, *v] for k, v in snap['staves'].items()]
            rows += [['BAR', *k, *v] for k, v in snap['bars'].items()]
            rows += [['OBJ', *k, bridge.fact_text(v)] for k, v in snap['objects'].items()]
            bridge.write_rows(baseline / name, rows)
        (baseline / 'verified.json').write_text(json.dumps(dict(ok=True, action='EXPORT')))
        (baseline / 'manifest.json').write_text(json.dumps(dict(part='1')))
        return baseline

    def test_part_edit_uses_and_freezes_exact_context_facts(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            baseline = self.part_baseline(Path(d))
            op = dict(id='offset', op='SET', staff=1, bar=1, ordinal=0, property='Dy', value=128)
            result = bridge.submit('APPLY', str(baseline), '1', [op])
            job = Path(result['job'])
            manifest = json.loads((job / 'manifest.json').read_text())
            self.assertEqual(bridge.fact(manifest['ops'][0][5])['Dy'], '64')
            self.assertEqual(manifest['context_sha256'], bridge.sha(baseline / 'context.tsv'))
            self.assertEqual((job / 'expected-context.tsv').read_bytes(), (baseline / 'context.tsv').read_bytes())
            self.assertEqual(bridge.snapshot(job / 'expected.tsv')['objects'][(1, 1, 0)]['Dy'], '0')

    def test_part_edit_rejects_wrong_part_and_musical_mutations(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            baseline = self.part_baseline(Path(d))
            graphical = dict(id='offset', op='SET', staff=1, bar=1, ordinal=0, property='Dy', value=128)
            with self.assertRaisesRegex(ValueError, 'exact part'):
                bridge.submit('APPLY', str(baseline), '2', [graphical])
            musical = dict(id='pitch', op='PITCH', staff=1, bar=1, ordinal=0, written_pitch=62, written_diatonic=36)
            with self.assertRaisesRegex(ValueError, 'graphical SET'):
                bridge.submit('APPLY', str(baseline), '1', [musical])

    def test_voice_recipe_rejects_gaps_and_overlaps(self):
        def event(name, position, duration):
            f = dict(fixture()['objects'][(1, 1, 0)])
            f.update(Position=str(position), Duration=str(duration))
            return dict(id=name, parent='', local_position=position, anchor='', fact=f)
        recipe = {'tuplets': [], 'events': [event('a', 0, 512), event('b', 512, 512)]}
        validate_recipe(recipe, 1024)
        for position in (256, 768):
            bad = copy.deepcopy(recipe); bad['events'][1]['local_position'] = position
            with self.assertRaises(ValueError):
                validate_recipe(bad, 1024)

    def test_voice_recipe_verifier_keeps_other_voices_and_text(self):
        before = fixture(); before['objects'][(1, 1, 1)] = dict(Type='Text', VoiceNumber='0', Text='keep')
        replacement = dict(before['objects'][(1, 1, 0)]); replacement['Duration'] = '1024'
        recipe = {'tuplets': [], 'events': [dict(id='a', parent='', local_position=0, anchor='', fact=replacement)]}
        op = dict(id='rhythm', op='REPLACE_VOICE', staff=1, bar=1, voice=1, recipe=recipe)
        row = bridge.compile_operation(op, before)
        after = copy.deepcopy(before); after['objects'][(1, 1, 0)] = replacement
        self.assertFalse(bridge.verify_changes(before, after, [row], [op]))
        after['objects'][(1, 1, 1)]['Text'] = 'changed'
        self.assertTrue(bridge.verify_changes(before, after, [row], [op]))

    def batch_fixture(self):
        snap = fixture()
        snap['score'][4] = '2'
        snap['staves'][2] = list(snap['staves'][1])
        for staff in (1, 2):
            for bar in (1, 2):
                snap['bars'][(staff, bar)] = list(snap['bars'][(1, 1)])
                snap['bars'][(staff, bar)][0] = str(bar)
                note = dict(snap['objects'][(1, 1, 0)])
                note['Duration'] = '1024'
                snap['objects'][(staff, bar, 0)] = note
        snap['objects'][(1, 1, 1)] = dict(Type='Text', VoiceNumber='0', Text='keep')
        other_voice = dict(snap['objects'][(1, 1, 0)], VoiceNumber='2', Voices='2')
        snap['objects'][(1, 1, 2)] = other_voice
        return snap

    def batch_operations(self, snap, targets=((1, 1), (1, 2), (2, 1))):
        ops = []
        for index, (staff, bar) in enumerate(targets):
            note = dict(snap['objects'][(staff, bar, 0)])
            note['Duration'] = '512'
            second = dict(note, Position='512')
            recipe = dict(tuplets=[], events=[
                dict(id='first', parent='', local_position=0, anchor='', fact=note),
                dict(id='second', parent='', local_position=512, anchor='', fact=second)])
            ops.append(dict(id=f'rebuild_{index}', op='REPLACE_VOICE', staff=staff,
                            bar=bar, voice=1, recipe=recipe))
        return ops

    def test_rebuild_batch_verifies_every_bar_and_preserves_other_material(self):
        before = self.batch_fixture()
        ops = self.batch_operations(before)
        rows = [bridge.compile_operation(op, before) for op in ops]
        bridge.validate_operation_batch(rows)
        after = copy.deepcopy(before)
        for op in ops:
            bar = (op['staff'], op['bar'])
            del after['objects'][(*bar, 0)]
            for index, event in enumerate(op['recipe']['events'], 10):
                after['objects'][(*bar, index)] = dict(event['fact'])
        self.assertFalse(bridge.verify_changes(before, after, rows, ops))
        # A wrong event in the final rebuilt bar must not escape a batch check.
        for address, prop, value in [((2, 1, 11), 'Duration', '256'),
                                     ((2, 2, 0), 'Hidden', 'true'),
                                     ((1, 1, 2), 'Hidden', 'true'),
                                     ((1, 1, 1), 'Text', 'changed')]:
            changed = copy.deepcopy(after)
            changed['objects'][address][prop] = value
            self.assertTrue(bridge.verify_changes(before, changed, rows, ops), address)

    def test_rebuild_batch_rejects_shared_bar_and_mixed_operations(self):
        before = self.batch_fixture()
        ops = self.batch_operations(before)
        rows = [bridge.compile_operation(op, before) for op in ops]
        duplicate = list(rows[0]); duplicate[1] = 'different_voice'; duplicate[7] = 2
        with self.assertRaisesRegex(ValueError, 'distinct staff/bar'):
            bridge.validate_operation_batch([rows[0], duplicate])
        ordinary = bridge.compile_operation(dict(id='ordinary', op='SET', staff=2,
            bar=2, ordinal=0, property='Hidden', value=True), before)
        with self.assertRaisesRegex(ValueError, 'cannot mix'):
            bridge.validate_operation_batch([rows[0], ordinary])

    def batch_baseline(self, root):
        baseline = root / 'jobs' / 'baseline'
        baseline.mkdir(parents=True)
        snap = self.batch_fixture()
        rows = [snap['score']]
        rows += [['STAFF', k, *v] for k, v in snap['staves'].items()]
        rows += [['BAR', *k, *v] for k, v in snap['bars'].items()]
        rows += [['OBJ', *k, bridge.fact_text(v)] for k, v in snap['objects'].items()]
        bridge.write_rows(baseline / 'before.tsv', rows)
        (baseline / 'verified.json').write_text(json.dumps(dict(ok=True, action='DISCOVER')))
        (baseline / 'manifest.json').write_text(json.dumps(dict(part='score')))
        return baseline, snap

    def test_rebuild_batch_freezes_every_recipe_and_validates_before_submission(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bridge, 'RUNTIME', Path(d)):
            root = Path(d)
            baseline, snap = self.batch_baseline(root)
            ops = self.batch_operations(snap)
            malformed = copy.deepcopy(ops)
            malformed[-1]['recipe']['events'][-1]['local_position'] = 256
            with self.assertRaises(ValueError):
                bridge.submit('APPLY', str(baseline), 'score', malformed)
            self.assertFalse((root / 'pending.txt').exists())
            self.assertEqual(list((root / 'jobs').iterdir()), [baseline])
            result = bridge.submit('APPLY', str(baseline), 'score', ops)
            job = Path(result['job'])
            manifest = json.loads((job / 'manifest.json').read_text())
            self.assertEqual(len(manifest['recipe_hashes']), 3)
            for name, checksum in manifest['recipe_hashes'].items():
                self.assertEqual(checksum, bridge.sha(job / name))
            self.assertEqual((job / 'expected.tsv').read_bytes(),
                             (baseline / 'before.tsv').read_bytes())


if __name__ == '__main__':
    unittest.main()
