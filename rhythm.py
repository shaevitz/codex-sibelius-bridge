"""Explicit, complete-voice recipes. No inference from the old MusicXML tables."""
from fractions import Fraction


def validate_recipe(recipe, bar_length):
    if set(recipe) != {'tuplets', 'events'} or not recipe['events']:
        raise ValueError('Recipe must contain tuplets and a nonempty event list')
    ids, tuplets, timeline = set(), {}, []
    for t in recipe['tuplets']:
        if set(t) != {'id', 'parent', 'local_position', 'fact'}:
            raise ValueError('Invalid tuplet recipe fields')
        if t['id'] in ids:
            raise ValueError('Duplicate recipe id')
        ids.add(t['id'])
        parent = t['parent']
        if parent and parent not in tuplets:
            raise ValueError('Tuplet parent must precede child')
        f = t['fact']
        if f['Type'] != 'Tuplet' or int(f['Left']) <= 0 or int(f['Right']) <= 0 or int(f['Unit']) <= 0:
            raise ValueError('Invalid tuplet ratio/unit')
        origin, scale = (tuplets[parent][:2] if parent else (Fraction(0), Fraction(1)))
        start = origin + int(t['local_position']) * scale
        duration = int(f['Unit']) * int(f['Right']) * scale
        if start < 0 or start + duration > bar_length:
            raise ValueError('Tuplet extends outside target bar')
        tuplets[t['id']] = (start, scale * Fraction(int(f['Right']), int(f['Left'])), f)
    events = {}
    for e in recipe['events']:
        if set(e) != {'id', 'parent', 'local_position', 'anchor', 'fact'} or e['id'] in ids:
            raise ValueError('Invalid or duplicate event recipe')
        ids.add(e['id'])
        f = e['fact']
        if f['Type'] != 'NoteRest' or int(f['Duration']) <= 0:
            raise ValueError('Each event must be a finite note/rest')
        notes = f['Notes'].split(';') if f['Notes'] else []
        if len(notes) != int(f['NoteCount']):
            raise ValueError('Chord note count differs')
        for n in notes:
            fields = n.split(',')
            if len(fields) != 13 or not all(0 <= int(fields[i]) <= 127 for i in (0, 2)):
                raise ValueError('Invalid sounding/written note contract')
        if e['parent'] and e['parent'] not in tuplets:
            raise ValueError('Event has unknown tuplet parent')
        origin, scale = tuplets[e['parent']][:2] if e['parent'] else (Fraction(0), Fraction(1))
        start = origin + int(e['local_position']) * scale
        duration = int(f['Duration']) * scale
        if f['Grace'] == 'true':
            if e['anchor'] not in events or not notes:
                raise ValueError('Grace requires a preceding ordinary-event anchor')
        else:
            if e['anchor']:
                raise ValueError('Ordinary event cannot have a grace anchor')
            if start < 0 or start + duration > bar_length:
                raise ValueError('Event extends outside target bar')
            timeline.append((start, start + duration))
        events[e['id']] = e
    cursor = Fraction(0)
    for start, end in sorted(timeline):
        if start != cursor:
            raise ValueError('Voice recipe has a gap or overlap')
        cursor = end
    if cursor != bar_length:
        raise ValueError('Voice recipe must fill the whole existing bar')


def extract_recipe(snap, staff, bar, voice):
    objects = [(addr, f) for addr, f in snap['objects'].items()
               if addr[:2] == (staff, bar) and f['VoiceNumber'] == str(voice)]
    tuples, parents = [], {}
    for addr, f in objects:
        if f['Type'] != 'Tuplet':
            continue
        key = (f['Position'], f['Left'], f['Right'], f['Unit'])
        if key in parents:
            raise ValueError('Coincident nested tuplets require an explicit parent recipe')
        parent = ''
        pos = int(f['Position'])
        if f.get('ParentTuplet'):
            bits = f['ParentTuplet'].split(',')
            parent = parents[tuple(bits[:4])]
            pos = int(bits[4])
        tid = f't{addr[2]}'
        parents[key] = tid
        tuples.append(dict(id=tid, parent=parent, local_position=pos, fact=dict(f)))
    ordinary, graces = [], []
    for addr, f in objects:
        if f['Type'] != 'NoteRest':
            continue
        parent, pos = '', int(f['Position'])
        if f.get('Tuplet'):
            bits = f['Tuplet'].split(',')
            parent = parents[tuple(bits[:4])]
            pos = int(bits[4])
        event = dict(id=f'e{addr[2]}', parent=parent, local_position=pos, anchor='', fact=dict(f))
        (graces if f['Grace'] == 'true' else ordinary).append(event)
    # Grace objects can enumerate before their anchors; place them after in the recipe.
    for grace in graces:
        candidates = [e for e in ordinary if e['fact']['Position'] == grace['fact']['Position']]
        if len(candidates) != 1:
            raise ValueError('Ambiguous grace anchor; specify anchor explicitly')
        grace['anchor'] = candidates[0]['id']
    recipe = {'tuplets': tuples, 'events': ordinary + graces}
    validate_recipe(recipe, int(snap['bars'][(staff, bar)][1]))
    return recipe
