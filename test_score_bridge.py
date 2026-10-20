import copy
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


if __name__ == '__main__':
    unittest.main()
