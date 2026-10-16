"""Opt-in self-hosted VLM preparation; no GPU/library imports or credentials."""
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/llmhost.json'


def settings():
    return json.loads(CONFIG.read_text())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def loopback(url):
    p = urlsplit(url)
    if (p.scheme != 'http' or p.hostname != '127.0.0.1' or not p.port
            or p.username or p.password or p.query or p.fragment
            or p.path != '/v1/chat/completions'):
        raise ValueError('loopback_chat_endpoint_required')
    return url


def images(request):
    values = []
    for message in request.get('messages', []):
        content = message.get('content', [])
        for part in content if isinstance(content, list) else []:
            if part.get('type') != 'image_url':
                continue
            url = part['image_url']['url']
            if not url.startswith(('data:image/jpeg;base64,', 'data:image/png;base64,')):
                raise ValueError('embedded_rgb_required')
            values.append(digest(base64.b64decode(url.split(',', 1)[1], validate=True)))
    if len(values) != 1:
        raise ValueError('exactly_one_own_rgb_required')
    return values


def check_alerts(directory=None):
    directory = Path(directory or Path.home() / 'projects/ugrp/outputs/model-endpoint-alerts')
    active = directory / 'last-alerts.json'
    failures = directory / 'check-failures.json'
    if active.exists() and json.loads(active.read_text()):
        raise ValueError('active_model_endpoint_alert')
    if failures.exists() and json.loads(failures.read_text()).get('consecutive', 0) >= 3:
        raise ValueError('model_endpoint_check_failed_3_times')


def identity(candidate):
    cfg = settings()
    model = cfg['models'][candidate]
    return dict(provider=cfg['provider'], candidate=candidate, endpoint=cfg['endpoint'],
                model=model['served_model'], repo=model['repo'], revision=model['revision'],
                quantization=model['quantization'], prefix_caching=True,
                allow_fallbacks=False, key_location='none; SSH loopback only')
