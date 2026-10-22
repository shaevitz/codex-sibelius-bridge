#!/usr/bin/env python3
"""Local, file-based controller for the Codex Score Bridge ManuScript plugin.

No score files are parsed or rewritten here. Native edits happen inside Sibelius.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid

from rhythm import extract_recipe, validate_recipe

# Installation and imports through a symlink must generate the same native build.
ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
VERSION = '1.2.0'
NOTE_FIELDS = ('Pitch', 'DiatonicPitch', 'WrittenPitch', 'WrittenDiatonicPitch',
               'Tied', 'TieStyle', 'NoteStyle', 'AccidentalStyle', 'Hidden',
               'Bracketed', 'LvTie', 'TiedInto', 'TieIntoStyle')
BOOL_KEYS = {'Hidden', 'CueSize', 'Magnetic', 'EraseBackground', 'FullDuration'}
INT_RANGES = {'Dx': (-32768, 32767), 'Dy': (-32768, 32767),
              'RhDx': (-32768, 32767), 'RhDy': (-32768, 32767),
              'Duration': (1, 1000000), 'SingleTremolos': (-1, 7),
              'DoubleTremolos': (0, 7), 'Beam': (0, 20),
              'RestPosition': (-1000, 1000), 'Size': (0, 3),
              'Bracket': (0, 2), 'TupletStyle': (0, 4)}


MUSIC_TEXT_PREFIX = chr(92) + 'i' + chr(92) * 2 + 'ctext.character.musictext' + chr(92)
BOLD_ROMAN_PREFIX = chr(92) + 'B' + chr(92) * 2 + 'i' + chr(92)


def music_dynamic(text):
    """Use the score's native music-text character style for dynamic glyphs."""
    if not isinstance(text, str) or not re.fullmatch(r'[fmpnrsz]{1,12}', text):
        raise ValueError('Music-text dynamics require only dynamic glyph letters')
    return MUSIC_TEXT_PREFIX + text


def dynamic_plain(value):
    if value.startswith(MUSIC_TEXT_PREFIX):
        text = value[len(MUSIC_TEXT_PREFIX):]
        music_dynamic(text)
        return text
    return None


def bold_roman(text):
    if not isinstance(text, str) or not text or '\\' in text or any(ord(c) < 32 for c in text):
        raise ValueError('Bold Roman prose must be nonempty plain text')
    return BOLD_ROMAN_PREFIX + text


def formatted_plain(value):
    if value.startswith(BOLD_ROMAN_PREFIX):
        text = value[len(BOLD_ROMAN_PREFIX):]
        bold_roman(text)
        return text
    return dynamic_plain(value)


def enc(value):
    return str(value).replace('%', '%25').replace('|', '%7C').replace('\r', '%0D').replace('\n', '%0A')


def dec(value):
    return value.replace('%0A', '\n').replace('%0D', '\r').replace('%7C', '|').replace('%25', '%')


def read_rows(path):
    return [[dec(v) for v in line.split('|')] for line in Path(path).read_text(encoding='utf-16').splitlines() if line]


def write_rows(path, rows):
    Path(path).write_text(''.join('|'.join(enc(v) for v in row) + '\n' for row in rows), encoding='utf-16')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fact(raw):
    return {k: dec(v) for k, v in (item.split('=', 1) for item in raw.split('|'))}


def fact_text(values):
    return '|'.join(f'{k}={enc(v)}' for k, v in values.items())


def snapshot(path):
    rows = read_rows(path)
    score = rows[0]
    if score[0] != 'SCORE' or len(score) != 6:
        raise ValueError('Invalid native snapshot header')
    objects, bars, staves = {}, {}, {}
    for row in rows[1:]:
        if row[0] == 'OBJ':
            key = tuple(map(int, row[1:4]))
            if key in objects:
                raise ValueError('Duplicate native object address')
            objects[key] = fact(row[4])
        elif row[0] == 'BAR':
            bars[tuple(map(int, row[1:3]))] = row[3:]
        elif row[0] == 'STAFF':
            staves[int(row[1])] = row[2:]
        else:
            raise ValueError(f'Unknown snapshot record {row[0]}')
    return {'score': score, 'objects': objects, 'bars': bars, 'staves': staves}


def strict_int(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def boolean(value):
    if not isinstance(value, bool):
        raise ValueError('Boolean property requires true or false')
    return '1' if value else '0'


def native_bool(value):
    return 'true' if value in (True, '1', 1) else 'false'


def transpose_interval(old_pitch, old_dia, new_pitch, new_dia):
    degree = new_dia - old_dia
    if degree == 0:
        interval = 5 + new_pitch - old_pitch
        strict_int(interval, 0, 10, 'chromatic unison')
        return 0, interval
    direction = 1 if degree > 0 else -1
    span = abs(degree)
    nominal = (0, 2, 4, 5, 7, 9, 11)[span % 7] + 12 * (span // 7)
    deviation = direction * (new_pitch - old_pitch) - nominal
    interval = 5 + deviation
    strict_int(interval, 0, 10, 'interval type')
    return degree, interval


def compile_operation(op, snap):
    allowed_fields = {'id', 'op', 'staff', 'bar', 'ordinal', 'property', 'value',
                      'note', 'written_pitch', 'written_diatonic', 'position',
                      'voice', 'style', 'duration', 'text', 'symbol', 'size', 'playback', 'recipe', 'music_text'}
    unknown = set(op) - allowed_fields
    if unknown:
        raise ValueError(f'Unknown operation fields: {sorted(unknown)}')
    if not isinstance(op.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', op['id']):
        raise ValueError('Each operation needs a unique alphanumeric id')
    sn = strict_int(op['staff'], 0, int(snap['score'][3]), 'staff')
    bn = strict_int(op['bar'], 1, int(snap['score'][4]), 'bar')
    kind = op['op']
    if 'music_text' in op and (kind != 'ADD_TEXT' or not isinstance(op['music_text'], bool)):
        raise ValueError('music_text is a Boolean option for ADD_TEXT only')
    ordinal = strict_int(op.get('ordinal', -1), -1, 100000, 'ordinal')
    target = snap['objects'].get((sn, bn, ordinal))
    row = ['OP', op['id'], sn, bn, ordinal, '', kind, '', '', '', '', '']
    if kind == 'REPLACE_VOICE':
        if sn == 0 or ordinal != -1:
            raise ValueError('Replace-voice targets one staff/bar, without an ordinal')
        voice = strict_int(op['voice'], 1, 4, 'voice')
        validate_recipe(op['recipe'], int(snap['bars'][(sn, bn)][1]))
        for entry in op['recipe']['tuplets'] + op['recipe']['events']:
            if entry['fact']['VoiceNumber'] != str(voice):
                raise ValueError('Recipe voice differs from target')
        for address, item in snap['objects'].items():
            if address[:2] == (sn, bn) and item['Type'] == 'Slur' and item['VoiceNumber'] == '0':
                raise ValueError('Shared-voice slur requires an explicit adapter')
        row[7] = voice
        return row
    if kind in {'ADD_TEXT', 'ADD_LINE', 'ADD_SYMBOL'}:
        if ordinal != -1:
            raise ValueError('Add operations must omit ordinal')
        pos = strict_int(op['position'], 0, int(snap['bars'][(sn, bn)][1]) - 1, 'position')
        voice = strict_int(op.get('voice', 0), 0, 4, 'voice')
        row[9:11] = [pos, voice]
        if kind == 'ADD_TEXT':
            style = op['style']
            prefix = 'text.system.' if sn == 0 else 'text.staff.'
            if not style.startswith(prefix):
                raise ValueError('Text style must match staff/system attachment')
            text = op['text']
            if op.get('music_text', False):
                if style != 'text.staff.expression':
                    raise ValueError('Music-text dynamics require expression style')
                text = music_dynamic(text)
            row[7:9] = [style, text]
        elif kind == 'ADD_LINE':
            if not op['style'].startswith('line.staff.') or sn == 0:
                raise ValueError('Only staff lines are supported; structure is settled')
            row[7:9] = [op['style'], strict_int(op['duration'], 1, 1000000, 'duration')]
            row[11] = boolean(op.get('playback', False))
        else:
            row[7:9] = [strict_int(op['symbol'], 0, 10000, 'symbol'), strict_int(op.get('size', 0), 0, 3, 'size')]
        for key, existing in snap['objects'].items():
            if key[:2] != (sn, bn) or existing['Position'] != str(pos):
                continue
            same = (kind == 'ADD_TEXT' and existing.get('StyleId') == op['style'] and existing.get('Text') == op['text']) or (kind == 'ADD_LINE' and existing.get('StyleId') == op['style'] and existing.get('Duration') == str(op['duration'])) or (kind == 'ADD_SYMBOL' and existing.get('Index') == str(op['symbol']))
            if same:
                raise ValueError('Matching object already exists; inspect instead of adding a duplicate')
        return row
    if target is None:
        raise ValueError('Target ordinal is absent from baseline')
    row[5] = fact_text(target)
    if kind == 'SET':
        prop, value = op['property'], op['value']
        valid = set(BOOL_KEYS) | set(INT_RANGES) | {'Text', 'StyleId'}
        if prop not in valid or prop not in target:
            raise ValueError('Unsupported property for this object')
        if prop == 'RestPosition' and int(target.get('NoteCount', '-1')) != 0:
            raise ValueError('RestPosition requires a rest')
        if prop in {'SingleTremolos', 'DoubleTremolos'} and int(target.get('NoteCount', '0')) == 0:
            raise ValueError('Tremolos require a pitched or percussion note')
        if prop in BOOL_KEYS:
            value = boolean(value)
        elif prop in INT_RANGES:
            value = strict_int(value, *INT_RANGES[prop], prop)
        elif not isinstance(value, str):
            raise ValueError('Text/style must be a string')
        if prop == 'Text':
            formatted_plain(value)  # Validate our supported native formatting prefixes.
        row[7:9] = [prop, value]
    elif kind == 'ARTICULATION':
        if target['Type'] != 'NoteRest':
            raise ValueError('Articulation target must be NoteRest')
        row[7:9] = [strict_int(op['property'], 0, 15, 'articulation'), boolean(op['value'])]
    elif kind in {'PITCH', 'NOTE_SET'}:
        ni = strict_int(op.get('note', 0), 0, int(target.get('NoteCount', '0')) - 1, 'note')
        row[9] = ni
        if kind == 'PITCH':
            if sn == 0:
                raise ValueError('Pitch target cannot be system staff')
            n = target['Notes'].split(';')[ni].split(',')
            pitch = strict_int(op['written_pitch'], 0, 127, 'written_pitch')
            dia = strict_int(op['written_diatonic'], 0, 100, 'written_diatonic')
            degree, interval = transpose_interval(int(n[2]), int(n[3]), pitch, dia)
            row[7:9], row[10:12] = [degree, interval], [dia, pitch]
        else:
            prop, value = op['property'], op['value']
            if prop == 'TieStyle' and target['Notes'].split(';')[ni].split(',')[4] != 'true':
                raise ValueError('Tie style requires an existing outgoing tie')
            if prop not in NOTE_FIELDS[4:10]:
                raise ValueError('Unsupported note property')
            if prop in {'Tied', 'Hidden', 'Bracketed', 'LvTie', 'TiedInto'}:
                value = boolean(value)
            elif prop in {'TieStyle', 'TieIntoStyle'}:
                if value not in {'Solid', 'Dashed', 'Dotted'}:
                    raise ValueError('Invalid tie style')
            else:
                value = strict_int(value, 0, 100 if prop == 'NoteStyle' else 3, prop)
            row[7:9] = [prop, value]
    elif kind == 'DELETE':
        if target['Type'] not in {'Text', 'SystemTextItem', 'SymbolItem', 'SystemSymbolItem'} and 'RhDx' not in target:
            raise ValueError('Deleting notes/structure requires the rhythm adapter')
    else:
        raise ValueError(f'Unsupported operation {kind}')
    return row


def install(destination=None):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    os.chmod(RUNTIME, 0o700)
    destination = Path(destination or Path.home() / 'Library/Application Support/Avid/Sibelius/Plugins/Codex/ScoreBridge.plg')
    text = native_source()
    text = text.replace('__BUILD__', hashlib.sha256(text.encode()).hexdigest())
    methods = re.split(r'(?m)^([A-Z]\w*) \(([^\n]*)\) \{\n', text)
    if methods[0].strip() or (len(methods) - 1) % 3:
        raise ValueError('Invalid ManuScript methods source')
    body = ['{']
    for i in range(1, len(methods), 3):
        name, args, code = methods[i:i+3]
        if not code.rstrip().endswith('}'):
            raise ValueError(f'Method {name} is incomplete')
        method = '(' + args + ') {\n' + code.rstrip()[:-1] + '}'
        body.append('\t' + name + ' "' + method.replace('\\', '\\\\').replace('"', '\\"') + '"')
    body.append('}\n')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        old = destination.read_bytes()
        archive = ROOT / 'install-history' / (hashlib.sha256(old).hexdigest() + '.plg')
        archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            archive.write_bytes(old)
    destination.write_text('\n'.join(body), encoding='utf-16')
    return {'installed': str(destination), 'sha256': sha(destination), 'version': VERSION,
            'activation': 'Restart Sibelius or reload via its plugin editor, then run Codex Score Bridge.'}


def native_source():
    return ((ROOT / 'ScoreBridge.methods.txt').read_text() + '\n' +
            (ROOT / 'Rhythm.methods.txt').read_text()).replace('__RUNTIME__', str(RUNTIME)).replace('__BRIDGE__', str(ROOT)).replace('__VERSION__', VERSION)


def resolve_job(job):
    p = Path(job)
    if not p.is_dir():
        p = RUNTIME / 'jobs' / job
    if not (p / 'manifest.json').exists():
        raise ValueError('Unknown job')
    return p


def validate_operation_batch(ops):
    """Rebuild batches contain only independent staff/bar targets.

    Rebuilding invalidates native object handles within its bar. Keep ordinary
    edits separate and refuse even different voices in the same staff/bar.
    """
    rebuilds = [row for row in ops if row[6] == 'REPLACE_VOICE']
    if not rebuilds:
        return
    if len(rebuilds) != len(ops):
        raise ValueError('Voice-rebuild batches cannot mix with other operations')
    bars = [(row[2], row[3]) for row in rebuilds]
    if len(set(bars)) != len(bars):
        raise ValueError('Voice-rebuild batches require distinct staff/bar targets')


def export_signatures(value):
    signatures = value.split(';')
    if not 1 <= len(signatures) <= 32 or len(set(signatures)) != len(signatures):
        raise ValueError('Export set requires 1..32 unique part selectors')
    for signature in signatures:
        if signature != 'score' and not re.fullmatch(r'[1-9]\d*(,[1-9]\d*)*(#[0-9]+)?', signature):
            raise ValueError('Invalid export set part selector')
    return signatures


def submit(action, baseline=None, part='score', operations=None, part_name=''):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pointer = RUNTIME / 'pending.txt'
        if pointer.exists():
            pending = Path(pointer.read_text(encoding='utf-16').strip())
            result = pending / 'verified.json'
            resolved = (pending / 'resolved.json').exists()
            if (not result.exists() or not json.loads(result.read_text())['ok']) and not resolved:
                raise ValueError(f'Unresolved request: {pending.name}. Collect or recover it first.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        job = RUNTIME / 'jobs' / (stamp + '-' + uuid.uuid4().hex[:12])
        snap = None
        if action != 'DISCOVER':
            source = resolve_job(baseline)
            verified = json.loads((source / 'verified.json').read_text())
            if not verified['ok']:
                raise ValueError('Baseline has not passed host verification')
            if verified.get('baseline_usable') is False or verified['action'] == 'EXPORT_PROOF':
                raise ValueError('PDF-only proof exports are not native edit baselines; use the last guarded job or discover again')
            source_path = source / ('after.tsv' if (source / 'after.tsv').exists() and verified['action'] in {'APPLY','ENSURE_PART'} else 'before.tsv')
            snap = snapshot(source_path)
            part_pattern = r'[1-9]\d*(,[1-9]\d*)*(#[0-9]+)?' if action in {'EXPORT','INSPECT','PREVIEW','APPLY'} else r'[1-9]\d*(,[1-9]\d*)*'
            if action in {'EXPORT_SET', 'EXPORT_PROOF'}:
                export_signatures(part)
            elif part != 'score' and not re.fullmatch(part_pattern, part):
                raise ValueError('Part is score or a comma-separated full-score staff signature')
        ops = []
        context_path = None
        compile_snap = snap
        if action in {'PREVIEW', 'APPLY'} and part != 'score':
            source_manifest = json.loads((source / 'manifest.json').read_text())
            context_path = source / ('context-after.tsv' if (source / 'context-after.tsv').exists() else 'context.tsv')
            if source_manifest['part'] != part or not context_path.exists():
                raise ValueError('Part edits require a verified export/part-edit baseline for that exact part')
            compile_snap = snapshot(context_path)
            if not operations or any(op.get('op') != 'SET' or op.get('property') not in
                                     {'Dx', 'Dy', 'RhDx', 'RhDy', 'Hidden', 'Magnetic'} for op in operations):
                raise ValueError('Part context permits only graphical SET operations')
        if action in {'PREVIEW', 'APPLY'}:
            if not operations or not isinstance(operations, list):
                raise ValueError('A nonempty JSON operation list is required')
            if snap['score'][5] not in {'true', 'True', '1'}:
                raise ValueError('Baseline must use transposing score mode')
            ops = [compile_operation(op, compile_snap) for op in operations]
            ids = [op[1] for op in ops]
            targets = [(op[2], op[3], op[4]) for op in ops if op[4] != -1]
            if len(set(ids)) != len(ids) or len(set(targets)) != len(targets):
                raise ValueError('Duplicate operation id or target; use sequential requests')
            validate_operation_batch(ops)
        job.mkdir(parents=True)
        recipe_hashes = {}
        for op, row in zip(operations or [], ops):
            if op['op'] != 'REPLACE_VOICE':
                continue
            recipe_path = job / ('recipe-' + op['id'] + '.tsv')
            rows = []
            for entry in op['recipe']['tuplets']:
                f = entry['fact']
                rows.append(['T', entry['id'], entry['parent'], entry['local_position'],
                             f['Left'], f['Right'], f['Unit'], f['TupletStyle'], f['Bracket'],
                             f['FullDuration'], fact_text(f), ''])
            for entry in op['recipe']['events']:
                f = entry['fact']
                rows.append(['E', entry['id'], entry['parent'], entry['local_position'],
                             f['Duration'], f['Notes'], fact_text(f), entry['anchor'],
                             f['Slash'], '', '', ''])
            write_rows(recipe_path, rows)
            recipe_hashes[recipe_path.name] = sha(recipe_path)
            row[8] = str(recipe_path)
        contract = snap['score'][1:] if snap else ['', '', 0, 0, '']
        # title, filename, staff count, bar count, transposing flag
        contract = contract
        header = ['CSB1', job.name, action, *contract, part, 1, 0, part_name, '', '']
        if len(header) != 14:
            raise AssertionError(header)
        write_rows(job / 'request.tsv', [header, *ops])
        if snap and action in {'PREVIEW', 'APPLY', 'ENSURE_PART'}:
            shutil.copyfile(source_path, job / 'expected.tsv')
        if context_path is not None:
            shutil.copyfile(context_path, job / 'expected-context.tsv')
        manifest = {'version': VERSION, 'id': job.name, 'action': action, 'part': part,
                    'baseline': str(source) if snap else None, 'operations': operations or [],
                    'request_sha256': sha(job / 'request.tsv'), 'ops': ops,
                    'recipe_hashes': recipe_hashes,
                    'context_sha256': sha(job / 'expected-context.tsv') if context_path is not None else None}
        (job / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        write_rows(pointer, [[str(job)]])
        return {'job': str(job), 'action': action, 'next': 'Run Codex Score Bridge in Sibelius, then collect this job.'}


def expected_target(before, row):
    result = dict(before)
    kind, prop, val = row[6:9]
    if kind == 'SET':
        result[prop] = native_bool(val) if prop in BOOL_KEYS else str(val)
        if prop == 'Magnetic':
            result['MagneticOverride'] = 'true'
        if prop == 'Text':
            plain = formatted_plain(val)
            if plain is not None:
                result['Text'] = plain
                result['Formatting'] = val
            else:
                # Legacy plain text may have native style serialization differences.
                result.pop('Formatting', None)
        if prop == 'Duration':
            result.pop('EndBar', None)
            result.pop('EndPosition', None)
    elif kind == 'ARTICULATION':
        values = result['Articulations'].split(',')
        values[int(prop)] = native_bool(val)
        result['Articulations'] = ','.join(values)
    elif kind in {'NOTE_SET', 'PITCH'}:
        notes = [n.split(',') for n in result['Notes'].split(';')]
        n = notes[int(row[9])]
        if kind == 'PITCH':
            offset, dia_offset = int(n[2]) - int(n[0]), int(n[3]) - int(n[1])
            n[:4] = [str(int(row[11]) - offset), str(int(row[10]) - dia_offset), str(row[11]), str(row[10])]
        else:
            n[NOTE_FIELDS.index(prop)] = native_bool(val) if prop in {'Tied', 'Hidden', 'Bracketed', 'LvTie', 'TiedInto'} else str(val)
            if prop == 'Tied':
                n[5] = (n[5] if n[5] not in {'', 'none'} else 'solid') if val == '1' else 'none'
            elif prop == 'TieStyle':
                n[5] = str(val).lower()
        notes.sort(key=lambda n: (int(n[1]), int(n[0])))
        result['Notes'] = ';'.join(','.join(n) for n in notes)
        if kind == 'PITCH':
            result.pop('Stemweight', None)  # Derived from pitches; verified in native/PDF proof.
    return result


def verify_changes(before, after, ops, operations=None):
    errors = []
    if before['score'] != after['score'] or before['staves'] != after['staves']:
        errors.append('Score/staff identity changed')
    # Page/system indices are derived layout; meter lengths/instrument identities/breaks must match.
    for key in before['bars'].keys() | after['bars'].keys():
        left, right = before['bars'].get(key), after['bars'].get(key)
        if left is None or right is None or left[:3] + left[5:] != right[:3] + right[5:]:
            errors.append(f'Bar structure/instrument changed: {key}')
    expected = defaultdict(list)
    for address, values in before['objects'].items():
        expected[address[:2]].append((address, dict(values)))
    for row in ops:
        bar = tuple(map(int, row[2:4])); ordinal = int(row[4])
        if row[6] == 'REPLACE_VOICE':
            recipe = next(op['recipe'] for op in operations if op['id'] == row[1])
            voice = str(row[7])
            expected[bar] = [(addr, f) for addr, f in expected[bar]
                             if not (f['VoiceNumber'] == voice and f['Type'] in {'NoteRest', 'BarRest', 'Tuplet'})]
            for entry in recipe['tuplets'] + recipe['events']:
                expected[bar].append((None, dict(entry['fact'])))
            continue
        if ordinal == -1:
            continue
        address = (*bar, ordinal)
        items = expected[bar]
        for index, (key, values) in enumerate(items):
            if key == address:
                if row[6] == 'DELETE':
                    items.pop(index)
                else:
                    items[index] = (key, expected_target(values, row))
                break
        else:
            errors.append(f'Missing expected target {address}')
    actual = defaultdict(list)
    for address, values in after['objects'].items():
        actual[address[:2]].append(dict(values))
    if any(row[6] in {'PITCH', 'REPLACE_VOICE'} for row in ops):
        # Stemweight is derived for an entire beam group, not an editable note flag.
        for items in expected.values():
            for _, values in items:
                values.pop('Stemweight', None)
        for items in actual.values():
            for values in items:
                values.pop('Stemweight', None)
    for row in ops:
        bar = tuple(map(int, row[2:4]))
        if row[6] not in {'ADD_TEXT', 'ADD_LINE', 'ADD_SYMBOL'}:
            continue
        matches = []
        for index, values in enumerate(actual[bar]):
            if values['Position'] != str(row[9]):
                continue
            if row[6] == 'ADD_TEXT':
                plain = formatted_plain(row[8])
                good = values.get('StyleId') == row[7] and values.get('Text') == (row[8] if plain is None else plain) and values['VoiceNumber'] == str(row[10])
                if plain is not None:
                    good = good and values.get('Formatting') == row[8]
            elif row[6] == 'ADD_LINE':
                # Sibelius supports playback passes 1–8. The legacy snapshot also
                # queries pass 9, which is out of range and always returns false.
                expected_played = ','.join([native_bool(row[11])] * 8 + ['false'])
                good = values.get('StyleId') == row[7] and values.get('Duration') == str(row[8]) and values['VoiceNumber'] == str(row[10]) and values['Played'] == expected_played
            else:
                good = values.get('Index') == str(row[7]) and values.get('Size') == str(row[8])
            if good:
                matches.append(index)
        if len(matches) != 1:
            errors.append(f'Addition not unique or did not match: {row[1]}')
        else:
            actual[bar].pop(matches[0])
    # Counter comparison tolerates native enumeration changes but preserves multiplicities.
    for bar in expected.keys() | actual.keys():
        wanted = [values for _, values in expected[bar]]
        got = actual[bar]
        # Normalize only declared derived fields on the one corresponding changed object.
        for row in ops:
            if tuple(map(int, row[2:4])) != bar or row[6] not in {'PITCH', 'SET'}:
                continue
            if row[6] == 'PITCH':
                drop = 'Stemweight'
            elif row[7] == 'Text':
                if formatted_plain(row[8]) is not None:
                    continue  # Explicit music-text formatting is compared exactly.
                drop = 'Formatting'
            elif row[7] == 'Duration':
                target = expected_target(before['objects'][(*bar, int(row[4]))], row)
                for obj in got:
                    if all(obj.get(k) == v for k, v in target.items()):
                        obj.pop('EndBar', None)
                        obj.pop('EndPosition', None)
                continue
            else:
                continue
            target = expected_target(before['objects'][(*bar, int(row[4]))], row)
            for obj in got:
                if all(obj.get(k) == v for k, v in target.items()):
                    obj.pop(drop, None)
        canonical = lambda values: json.dumps(values, sort_keys=True)
        if Counter(map(canonical, wanted)) != Counter(map(canonical, got)):
            errors.append(f'Unexpected object changes in staff/bar {bar}')
    return errors


def pdf_set(job, selectors):
    """Validate every requested PDF; never silently accept a partial export."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    pdfs, errors = {}, []
    for signature in export_signatures(selectors):
        pdf = job / f'part-{signature}.pdf'
        try:
            pages = len(PdfReader(pdf).pages)
            if not pages:
                raise ValueError('Empty exported PDF')
            pdfs[signature] = dict(pdf=str(pdf), pages=pages, sha256=sha(pdf))
        except (OSError, ValueError, PdfReadError) as exc:
            errors.append(f'Export {signature}: {exc}')
    return pdfs, errors


def collect(job):
    job = resolve_job(job)
    manifest = json.loads((job / 'manifest.json').read_text())
    if sha(job / 'request.tsv') != manifest['request_sha256']:
        raise ValueError('Request was modified after submission')
    for filename, digest in manifest.get('recipe_hashes', {}).items():
        if sha(job / filename) != digest:
            raise ValueError('Voice recipe was modified after submission')
    if manifest.get('context_sha256') and sha(job / 'expected-context.tsv') != manifest['context_sha256']:
        raise ValueError('Part baseline was modified after submission')
    if not (job / 'status.tsv').exists():
        return {'job': job.name, 'ok': False, 'state': 'QUEUED'}
    states = read_rows(job / 'status.tsv')
    state = states[-1][0]
    result = {'job': job.name, 'action': manifest['action'], 'state': state, 'ok': False, 'errors': []}
    if state in {'RUNNING', 'HEADER_READ', 'MUTATING'}:
        return result
    if state == 'PDF_PROOF_EXPORTED' and manifest['action'] == 'EXPORT_PROOF':
        identity = read_rows(job / 'identity.tsv')
        expected = ['SCORE', *read_rows(job / 'request.tsv')[0][3:8]]
        if identity != [expected]:
            result['errors'].append('Proof export score identity differs from request')
        result['pdfs'], errors = pdf_set(job, manifest['part'])
        result['errors'] += errors
        result.update(baseline_usable=False, musical_state_verified=False,
                      part_contexts_included=False, requires_visual_review=True,
                      verification_scope='PDF readability, hashes and score identity only; no native musical snapshot')
        result['ok'] = not result['errors']
        (job / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    if state in {'DONE', 'PREVIEWED', 'EXPORTED_UNVERIFIED', 'APPLIED_UNVERIFIED'}:
        snap = snapshot(job / 'before.tsv')
        result['score'] = snap['score']
        result['object_count'] = len(snap['objects'])
        result['parts'] = read_rows(job / 'parts.tsv')
        if state == 'APPLIED_UNVERIFIED':
            if manifest.get('context_sha256'):
                result['errors'] += verify_changes(snap, snapshot(job / 'after.tsv'), [])
                result['errors'] += verify_changes(snapshot(job / 'context-before.tsv'),
                    snapshot(job / 'context-after.tsv'), manifest['ops'], manifest['operations'])
                result['edit_context'] = 'part'
                result['part_preservation_requires_pdf_check'] = True
            else:
                result['errors'] += verify_changes(snap, snapshot(job / 'after.tsv'), manifest['ops'], manifest['operations'])
            for filename in ('before.sib', 'candidate.sib'):
                p = job / filename
                if not p.exists() or p.stat().st_size < 100:
                    result['errors'].append(f'Native {filename} absent/empty')
                else:
                    result[filename + '_sha256'] = sha(p)
            result['candidate'] = str(job / 'candidate.sib')
            result['requires_visual_review'] = True
        if state == 'EXPORTED_UNVERIFIED':
            from pypdf import PdfReader
            if manifest['action'] == 'EXPORT_SET':
                source = resolve_job(manifest['baseline'])
                prior_result = json.loads((source / 'verified.json').read_text())
                prior_file = source / ('after.tsv' if prior_result['action'] in {'APPLY','ENSURE_PART'} else 'before.tsv')
                result['errors'] += verify_changes(snapshot(prior_file), snap, [])
                result['observed_full_score_matches_baseline'] = not result['errors']
                result['pdfs'], errors = pdf_set(job, manifest['part'])
                result['errors'] += errors
                result['part_contexts_included'] = False
            else:
                pdf = job / 'part.pdf'
                reader = PdfReader(pdf)
                if not reader.pages:
                    result['errors'].append('Empty exported PDF')
                result['pdf_pages'] = len(reader.pages)
                result['pdf_sha256'] = sha(pdf)
                result['pdf'] = str(pdf)
        result['ok'] = not result['errors']
    else:
        result['errors'].append(states[-1][1:] or [state])
    (job / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def invoke(method='Run', arguments=None, timeout=None):
    timeout = (1800 if method == 'Run' else 30) if timeout is None else timeout
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Timeout must be positive seconds')
    if method == 'Run':
        checked = invoke('ProtocolTest').get('returnValue', {})
        if checked.get('version') != VERSION or checked.get('build') != hashlib.sha256(native_source().encode()).hexdigest():
            raise ValueError('Sibelius has a different plugin build loaded. Reinstall and restart it.')
        if checked.get('original') != checked.get('roundtrip') or checked.get('encoded') != enc(checked.get('original', '')):
            raise ValueError('Native text encoding self-test failed')
        if checked.get('empty') != '' or checked.get('empty_equals') is not True:
            raise ValueError('Native empty-field conversion self-test failed')
    connection = json.loads((RUNTIME / 'connection.json').read_text())
    if connection['status'] != 'ready':
        raise ValueError(f"Local connection is {connection['status']}; inspect its current job")
    os.kill(connection['pid'], 0)
    invocation = {'id': uuid.uuid4().hex, 'method': method, 'args': arguments or []}
    if method == 'Run':
        invocation['job'] = (RUNTIME / 'pending.txt').read_text(encoding='utf-16').strip()
    staging = RUNTIME / 'invoke-next.json'
    staging.write_text(json.dumps(invocation))
    staging.replace(RUNTIME / 'invoke.json')
    reply = RUNTIME / ('reply-' + invocation['id'] + '.json')
    deadline = time.monotonic() + timeout
    while not reply.exists():
        state = json.loads((RUNTIME / 'connection.json').read_text())
        if state['status'] in {'disconnected','stopped','connection failed'}:
            raise ValueError('Sibelius connection ended during the request. Retain its recovery copy; do not retry blindly.')
        if time.monotonic() > deadline:
            job_name = Path(invocation.get('job', '')).name
            raise ValueError(f'Wait expired; native request may still be running. '
                             f'Invocation {invocation["id"]}, job {job_name or "none"}. '
                             'Use status/collect; do not submit or invoke it again.')
        time.sleep(0.2)
    result = json.loads(reply.read_text())
    if not result['result']:
        raise ValueError('Sibelius could not invoke the installed plugin/method')
    return result


def wait_for_score(path, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = invoke('ScoreStatus').get('returnValue', {})
        if value.get('active') and Path(value['filename']).resolve() == Path(path).resolve():
            return value
        time.sleep(0.2)
    raise ValueError('Sibelius has not activated the requested score')


def recover_job(job):
    job = resolve_job(job)
    backup = job / 'before.sib'
    if not backup.exists():
        raise ValueError('No native recovery copy exists')
    result = invoke('RecoverJob', [str(job)])
    if result.get('returnValue') is not True:
        raise ValueError('Native recovery refused; verify the active score')
    actual = wait_for_score(backup)
    header = read_rows(job / 'request.tsv')[0]
    if actual['title'] != header[3] or actual['bars'] != int(header[6]):
        raise ValueError('Recovered native score does not match its original title/bar count')
    resolved = {'recovered_from':str(backup), 'sha256':sha(backup), 'active_score':actual}
    (job / 'resolved.json').write_text(json.dumps(resolved) + '\n')
    return resolved


def job_status(job=None):
    """Read local evidence without invoking Sibelius or taking another inventory."""
    connection_path = RUNTIME / 'connection.json'
    connection = json.loads(connection_path.read_text()) if connection_path.exists() else {}
    alive = False
    if connection.get('pid'):
        try:
            os.kill(connection['pid'], 0)
            alive = True
        except ProcessLookupError:
            pass
    result = dict(connection=connection, daemon_process_alive=alive)
    if job is None and (RUNTIME / 'pending.txt').exists():
        job = (RUNTIME / 'pending.txt').read_text(encoding='utf-16').strip()
    if job:
        path = resolve_job(job)
        result['job'] = str(path)
        result['native_status'] = read_rows(path / 'status.tsv') if (path / 'status.tsv').exists() else [['QUEUED']]
        verified = json.loads((path / 'verified.json').read_text()) if (path / 'verified.json').exists() else None
        result['host_result'] = None if verified is None else {
            key: verified[key] for key in ('ok', 'action', 'state', 'errors', 'baseline_usable',
                                           'musical_state_verified', 'requires_visual_review') if key in verified}
        if verified and 'pdfs' in verified:
            result['pdf_count'] = len(verified['pdfs'])
            result['pdf_pages'] = sum(item['pages'] for item in verified['pdfs'].values())
        result['recovery_copy_exists'] = (path / 'before.sib').exists()
    result['note'] = 'Daemon liveness/status files do not establish native progress or musical correctness.'
    return result


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError('Timeout must be finite positive seconds')
    return seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('install'); p.add_argument('--destination')
    p = sub.add_parser('discover'); p.add_argument('--run', action='store_true'); p.add_argument('--timeout', type=positive_seconds, default=1800)
    for cmd in ('inspect', 'export', 'export-set', 'export-proof', 'preview', 'apply', 'ensure-part'):
        p = sub.add_parser(cmd); p.add_argument('--baseline', required=True); p.add_argument('--part', default='score')
        p.add_argument('--run', action='store_true')
        p.add_argument('--timeout', type=positive_seconds, default=1800)
        if cmd in {'preview', 'apply'}:
            p.add_argument('--operations', required=True, type=Path)
        if cmd == 'ensure-part':
            p.add_argument('--name', required=True)
    p = sub.add_parser('collect'); p.add_argument('job')
    p = sub.add_parser('invoke'); p.add_argument('--timeout', type=positive_seconds, default=1800)
    p = sub.add_parser('status'); p.add_argument('job', nargs='?')
    sub.add_parser('doctor')
    p = sub.add_parser('open'); p.add_argument('path', type=Path)
    p = sub.add_parser('show-part'); p.add_argument('--score', required=True, type=Path); p.add_argument('--part', required=True)
    p = sub.add_parser('recover'); p.add_argument('job')
    p = sub.add_parser('abandon'); p.add_argument('job'); p.add_argument('--reason', required=True)
    p = sub.add_parser('recipe'); p.add_argument('job'); p.add_argument('--staff', type=int, required=True); p.add_argument('--bar', type=int, required=True); p.add_argument('--voice', type=int, default=1)
    p = sub.add_parser('show'); p.add_argument('job'); p.add_argument('--staff', type=int); p.add_argument('--bars', default='1:99999'); p.add_argument('--context', choices=['score', 'part'], default='score')
    args = parser.parse_args()
    try:
        if args.command == 'install':
            result = install(args.destination)
        elif args.command == 'collect':
            result = collect(args.job)
        elif args.command == 'invoke':
            result = invoke(timeout=args.timeout)
        elif args.command == 'status':
            result = job_status(args.job)
        elif args.command == 'doctor':
            result = invoke('ProtocolTest')
        elif args.command == 'open':
            if not args.path.is_absolute() or args.path.suffix != '.sib' or not args.path.exists():
                raise ValueError('Open requires an existing absolute .sib path')
            result = invoke('OpenScore', [str(args.path)])
            if result.get('returnValue') is not True:
                raise ValueError('Sibelius could not open the score')
            result['active_score'] = wait_for_score(args.path)
        elif args.command == 'recover':
            result = recover_job(args.job)
        elif args.command == 'show-part':
            if not args.score.is_absolute() or args.score.suffix != '.sib':
                raise ValueError('Show part requires the exact absolute active score filename')
            if len(export_signatures(args.part)) != 1:
                raise ValueError('Show part requires one selector')
            result = invoke('ShowPart', [str(args.score), args.part])
            if not result.get('returnValue'):
                raise ValueError('Active score differs or part is missing/ambiguous')
        elif args.command == 'abandon':
            job = resolve_job(args.job)
            if (job / 'before.sib').exists():
                raise ValueError('A native recovery copy exists: recover the score before resolving this job')
            result = {'reason': args.reason, 'mutations_started': False}
            (job / 'resolved.json').write_text(json.dumps(result) + '\n')
        elif args.command == 'recipe':
            job = resolve_job(args.job)
            snap = snapshot(job / ('after.tsv' if (job / 'after.tsv').exists() else 'before.tsv'))
            result = extract_recipe(snap, args.staff, args.bar, args.voice)
        elif args.command == 'show':
            job = resolve_job(args.job)
            if args.context == 'part':
                snap = snapshot(job / ('context-after.tsv' if (job / 'context-after.tsv').exists() else 'context.tsv'))
            else:
                snap = snapshot(job / ('after.tsv' if (job / 'after.tsv').exists() else 'before.tsv'))
            first, last = map(int, args.bars.split(':'))
            result = [{'staff': k[0], 'bar': k[1], 'ordinal': k[2], **v} for k, v in snap['objects'].items() if (args.staff is None or k[0] == args.staff) and first <= k[1] <= last]
        else:
            ops = json.loads(args.operations.read_text()) if hasattr(args, 'operations') else None
            result = submit(args.command.upper().replace('-','_'), getattr(args, 'baseline', None), getattr(args, 'part', 'score'), ops, getattr(args,'name',''))
            if getattr(args, 'run', False):
                invoke(timeout=args.timeout)
                result = collect(result['job'])
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
