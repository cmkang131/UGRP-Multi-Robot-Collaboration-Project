"""Read-only evidence discovery for retention proposals, never a deletion tool.

References are recognized by their contents, including dictionary *keys*, not by
the name of the containing log. Ambiguous relative paths protect every matching
suffix. A digest protects every byte-identical file, not just a preferred copy.
The batch-specific driver records graph edges and conservative directory edges.
"""
from __future__ import annotations

import base64
import binascii
import csv
import fnmatch
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import re


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
STRUCTURED_EXTENSIONS = {'.json', '.jsonl', '.csv', '.tsv'}
TEXT_EXTENSIONS = {'.log', '.txt'}
HASH = re.compile(r'(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])')
# JSON strings are decoded before extraction, so spaces and escaped separators
# in a whole path are retained. This expression also finds paths inside prose.
IMAGE = re.compile(r'(?<![^\s\"\'`<>|,;=\[\]{}()])[^\s\"\'`<>|,;=\[\]{}()]+\.(?:jpe?g|png|webp|bmp|tiff?)(?![\w.])', re.I)
OUTPUT_PATH = re.compile(r'(?<![^\s\"\'`<>|,;=\[\]()])(?:[^\s\"\'`<>|,;=\[\]()]*?/)?outputs/[^\s\"\'`<>|,;=\[\]()]+')


def under(path: str, folder: str) -> bool:
    return not folder or path == folder or path.startswith(folder + '/')


def exclusion_ids(path, exclusions):
    """Use the review's exact fnmatchcase semantics (* can include /)."""
    matches = []
    for group in exclusions['exclusions']:
        for rule in group['exclude']:
            if rule['kind'] == 'folder':
                hit = under(path, rule['path'])
            elif rule['kind'] == 'glob':
                hit = fnmatch.fnmatchcase(path, rule['pattern'])
            else:
                raise ValueError(f"unknown reviewer exclusion kind: {rule['kind']}")
            if hit:
                matches.append(group['id'])
                break
    return matches


def structured_suffix(path):
    name = str(path).lower()
    if name.endswith('.gz'):
        name = name[:-3]
    suffix = PurePosixPath(name).suffix
    return suffix if suffix in STRUCTURED_EXTENSIONS | TEXT_EXTENSIONS else None


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def structured_strings(stream, suffix, *, streaming=True):
    """All JSON/JSONL fields and CSV cells; no filename/key allowlist.

    ijson is optional (used for the multi-GiB audit); the stdlib fallback keeps
    the helper/tests portable. Invalid input raises, so the driver can protect
    its producing family instead of treating an unreadable record as no edge.
    """
    if suffix in TEXT_EXTENSIONS:
        for line in stream:
            text = line.decode('utf-8', errors='strict')
            if text.lstrip().startswith(('{', '[')):
                try:
                    row = json.loads(text)
                except ValueError:
                    pass
                else:
                    yield from walk_strings(row)
                    yield from frame_references(row)
            yield text
        return
    if suffix in {'.csv', '.tsv'}:
        csv.field_size_limit(max(csv.field_size_limit(), 128 * 1024 * 1024))
        wrapper = io.TextIOWrapper(stream, encoding='utf-8-sig', errors='strict', newline='')
        try:
            for row in csv.reader(wrapper, delimiter='\t' if suffix == '.tsv' else ','):
                yield from row
        finally:
            wrapper.detach()
        return
    if suffix == '.jsonl':
        for line in stream:
            if line.strip():
                row = json.loads(line)
                yield from walk_strings(row)
                yield from frame_references(row)
        return
    if streaming:
        try:
            import ijson
        except ImportError:
            pass
        else:
            try:
                for event, value in ijson.basic_parse(stream):
                    if event in {'string', 'map_key'}:
                        yield value
            except ijson.JSONError:
                # Historical Python writers emitted NaN/Infinity. Re-read via
                # Python's decoder, preserving all string references. Truly
                # malformed records still raise and protect the producer.
                stream.seek(0)
                yield from walk_strings(json.load(stream))
            return
    yield from walk_strings(json.load(stream))


def normalize_reference(value):
    """Relocate historical absolute outputs roots; never access those roots."""
    value = value.replace('\\', '/').strip()
    if '/outputs/' in value:
        value = value.split('/outputs/', 1)[1]
    elif value.startswith('outputs/'):
        value = value[len('outputs/'):]
    elif value.startswith('/') or '://' in value:
        return None
    # Ambiguous parent-relative records are matched against every suffix too.
    value = posixpath.normpath(value)
    while value.startswith('../'):
        value = value[3:]
    return value.removeprefix('./') if value not in {'', '.', '..'} else None


def references(value):
    """Yield (kind, target) for paths, hashes, inline images, directory roots."""
    if len(value) >= 64:
        for match in HASH.finditer(value):
            yield 'sha256', match.group().lower()
    if value.startswith(('data:image/', '/9j/', 'iVBORw0KGgo')):
        if value.startswith('data:') and ',' not in value:
            raise ValueError('invalid inline image payload')
        encoded = value.split(',', 1)[1] if value.startswith('data:') else value
        try:
            yield 'sha256', hashlib.sha256(base64.b64decode(encoded, validate=True)).hexdigest()
        except (ValueError, binascii.Error):
            raise ValueError('invalid inline image payload') from None
        return
    candidates = set(IMAGE.findall(value)) if '.' in value else set()
    # An entire string may be a path containing spaces. Avoid swallowing prose.
    if value.lower().endswith(tuple(IMAGE_EXTENSIONS)) and '\n' not in value:
        candidates.add(value)
    for image in sorted(candidates):
        if normalized := normalize_reference(image):
            yield 'image', normalized
    for match in OUTPUT_PATH.finditer(value) if 'outputs/' in value else ():
        target = normalize_reference(match.group().rstrip('.:'))
        if target:
            yield 'output', target


def path_matches(path, target):
    return path == target or path.endswith('/' + target)


def glob_parent(target):
    """Protect the complete directory a glob traverses, not its sample hits."""
    first = min((target.find(c) for c in '*?[{' if c in target), default=-1)
    if first < 0:
        return target
    prefix = target[:first]
    return prefix.rstrip('/') if prefix.endswith('/') else prefix.rpartition('/')[0]


def matched_glob_folder(pattern, path, is_directory=False):
    """Resolve recursive discovery to the runs it actually reads.

    outputs/**/pair-decisions.json does not read unrelated node_modules. Keep
    the entire matched run directory (including sibling commands/images), not
    every unrelated top-level directory encountered while locating that run.
    """
    if not fnmatch.fnmatchcase(path, pattern):
        return None
    # A top-level log matching a family wildcard does not make every unrelated
    # run an input. The caller must retain that file as an exact path edge.
    return path if is_directory else (path.rpartition('/')[0] or None)


def frame_references(row):
    """Join the review's decomposed (run,case,robot,frame) frame table.

    Other implicit frame producers are covered by whole-run directory edges;
    a numeric frame identifier alone is never proof that its image is unused.
    """
    if not isinstance(row, dict):
        return []
    if (all(isinstance(row.get(k), str) for k in ('run', 'case', 'robot'))
            and isinstance(row.get('frame'), int) and row['frame'] >= 0):
        run = normalize_reference(row['run'])
        if run:
            return [f"{run}/cases/{row['case']}/frames/{row['robot']}/{row['frame']:05d}.jpg"]
    return []


def open_record(path):
    return gzip.open(path, 'rb') if str(path).lower().endswith('.gz') else Path(path).open('rb')
