#!/usr/bin/env python3
"""Preserve LLM text while excluding embedded image payloads; originals retained."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

IMAGE_KEYS = {'jpeg_base64', 'rgb_base64', 'image', 'image_url', 'b64_json', 'image_base64'}
DATA_IMAGE = re.compile(r'data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    if path.name.endswith('.zst'):
        return subprocess.run(['zstd', '-qdc', '--', str(path)], capture_output=True,
                              check=True).stdout
    return path.read_bytes()


def atomic(path, data):
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def omitted(value):
    raw = base64.b64decode(value, validate=True)
    return {'image_omitted': True, 'bytes': len(raw), 'sha256': sha(raw)}


def strip(value, key='', image_context=False):
    if isinstance(value, list):
        return [strip(v, key, image_context) for v in value]
    if isinstance(value, dict):
        image_context = image_context or str(value.get('mime_type', value.get('media_type', ''))).startswith('image/')
        image_context = image_context or value.get('type') in {'image', 'image_url', 'input_image'}
        return {k: strip(v, k, image_context) for k, v in value.items()}
    if not isinstance(value, str):
        return value
    if 'data:image/' in value:
        def replace(match):
            return 'image_omitted:' + sha(base64.b64decode(match.group().split(',', 1)[1], validate=True))
        value = DATA_IMAGE.sub(replace, value)
        if 'data:image/' in value:
            raise ValueError('UNRECOGNIZED_IMAGE_DATA_URL')
    if key in IMAGE_KEYS or (key == 'data' and image_context):
        if value and (key not in {'image', 'image_url'} or len(value) >= 32):
            try:
                return omitted(value)
            except (ValueError, base64.binascii.Error):
                pass
    if value.lstrip().startswith(('{', '[')) and any(k in value for k in IMAGE_KEYS):
        try:
            nested = json.loads(value)
        except ValueError:
            return value
        return json.dumps(strip(nested), ensure_ascii=False)
    return value


def export(root):
    root = root.resolve()
    if not (root / 'EXIT').is_file():
        raise ValueError('EXIT_REQUIRED')
    excluded = set()
    manifest = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink() or 'lite-text' in path.relative_to(root).parts:
            continue
        logical = path.name.removesuffix('.zst')
        if not logical.endswith(('.json', '.jsonl')) or path.name == 'LITE_TEXT_MANIFEST.json':
            continue
        data = read(path)
        tokens = (b'data:image/', b'jpeg_base64', b'rgb_base64', b'image_base64', b'b64_json',
                  b'"image"', b'"image_url"', b'"media_type"', b'"mime_type"')
        if not any(token in data for token in tokens):
            continue
        if logical.endswith('.jsonl'):
            values = [json.loads(line) for line in data.splitlines() if line.strip()]
            cleaned = [strip(v) for v in values]
            if cleaned == values:
                continue
            text = ''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in cleaned).encode()
        else:
            value = json.loads(data)
            cleaned = strip(value)
            if cleaned == value:
                continue
            text = (json.dumps(cleaned, ensure_ascii=False, indent=2) + '\n').encode()
        if b'data:image/' in text:
            raise ValueError('IMAGE_PAYLOAD_REMAINED')
        source = path.relative_to(root).as_posix().removesuffix('.zst')
        excluded.update(('/' + source, '/' + source + '.zst'))
        dest = root / 'lite-text' / source
        compressed = dest.with_name(dest.name + '.zst')
        if compressed.exists():
            if dest.exists() or read(compressed) != text:
                raise ValueError('EXISTING_LITE_TEXT_MISMATCH')
            dest = compressed
        elif dest.exists() and dest.read_bytes() != text:
            raise ValueError('EXISTING_LITE_TEXT_MISMATCH')
        else:
            atomic(dest, text)
        manifest.append({'source': source, 'source_candidates': [source, source + '.zst'],
                         'source_sha256': sha(data), 'source_stored': path.relative_to(root).as_posix(),
                         'source_stored_sha256': sha(path.read_bytes()),
                         'text': dest.relative_to(root).as_posix(),
                         'text_candidates': ['lite-text/' + source, 'lite-text/' + source + '.zst'],
                         'text_sha256': sha(text), 'text_stored_sha256': sha(dest.read_bytes())})
    atomic(root / 'LITE_IMAGE_EXCLUSIONS.txt', ('\n'.join(sorted(excluded)) + '\n').encode())
    atomic(root / 'LITE_TEXT_MANIFEST.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return {'embedded_image_files_excluded': len(manifest), 'text_copies': len(manifest)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    export(args.run)
