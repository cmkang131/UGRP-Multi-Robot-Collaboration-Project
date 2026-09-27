"""Weaker, explicit quota evidence for the audited ID-less local proxy.

No upstream IDs or non-billable retry usage are inferred. A complete window
accounts for attempts under #222; exact usage describes the FINAL response only.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
from zoneinfo import ZoneInfo

from harness.zone_pilot_budget import PROXY_SHA256, sha, usage_total

EVIDENCE_LEVEL = 'proxy_log_exclusive_window'
ID_EVIDENCE_LEVEL = 'proxy_upstream_ids'
ACCEPTED_EVIDENCE_LEVELS = (ID_EVIDENCE_LEVEL, EVIDENCE_LEVEL)
PADDING_SECONDS = 1
LIMITATION = ('quota_accounting_only; weaker_than_request_ids; final_response_usage_only; '
              'no_upstream_ids_or_finish_reason_verification; no_refunds')
STAMP = re.compile(rb'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*?)[\r\n]*$')
HTTP = re.compile(rb'^http "([A-Z]+) ([^" ]+) HTTP/\d(?:\.\d)?" (\d{3}) -$')
ERROR = re.compile(rb'error|exception|no_visible_text', re.I)


def _line(raw, zone):
    match = STAMP.fullmatch(raw)
    if not match:
        raise ValueError('unparseable_proxy_log_line')
    stamp = datetime.strptime(match[1].decode('ascii'), '%Y-%m-%d %H:%M:%S')
    return int(stamp.replace(tzinfo=zone).timestamp()), match[2]


def window_spec(sent, timezone):
    """Legacy original-file mtime bounds are explicit, never invented wire times.

    Request bytes are fsynced before wire; response mtime follows receipt. The
    legacy route additionally requires the ledger's contemporaneous byte seal.
    """
    ZoneInfo(timezone)
    ledger = sent['ledger']
    start, end = ledger.get('send_started_at_ns'), ledger.get('response_received_at_ns')
    source = 'ledger_wall_time_ns'
    if start is None and end is None:
        source = 'original_wire_file_mtime_ns_with_sealed_log_cursor'
        request = Path(sent['request_path'])
        start = request.stat().st_mtime_ns
        end = (request.parent / ledger['response_path']).stat().st_mtime_ns
    if any(type(t) is not int or t <= 0 for t in (start, end)) or end < start:
        raise ValueError('missing_or_invalid_send_response_times')
    return {'send_started_at_ns': start, 'response_received_at_ns': end,
            'time_source': source, 'log_timezone': timezone, 'log_resolution_seconds': 1,
            'padding_seconds': PADDING_SECONDS,
            'lower_epoch_second': start // 1_000_000_000 - PADDING_SECONDS,
            'upper_epoch_second': end // 1_000_000_000 + PADDING_SECONDS,
            'bounds': 'inclusive_floor_seconds_plus_padding'}


def extract_window(raw, window):
    """Keep exact contiguous bytes, including one bracketing line on each side.

    An absent bracket cannot demonstrate coverage, including at EOF. Unknown
    lines inside the bracket are preserved so validation fails closed on them.
    """
    zone = ZoneInfo(window['log_timezone'])
    lower, upper = window['lower_epoch_second'], window['upper_epoch_second']
    before, after, offset = None, None, 0
    for line in raw.splitlines(keepends=True):
        try:
            stamp, _ = _line(line, zone)
        except ValueError:
            stamp = None
        if stamp is not None and stamp < lower:
            before = offset
        if stamp is not None and stamp > upper and before is not None:
            after = offset + len(line)
            break
        offset += len(line)
    if before is None or after is None:
        raise ValueError('proxy_log_window_coverage_missing')
    return before, after, raw[before:after]


def _usage(sent):
    request = Path(sent['request_path'])
    if sha(request.read_bytes()) != sent['body_sha256']:
        raise ValueError('stored_request_hash_mismatch')
    payload = json.loads(request.read_bytes())
    if payload.get('stream') or sent['ledger'].get('method') != 'POST':
        raise ValueError('nonstream_post_required')
    response = (request.parent / sent['ledger']['response_path']).read_bytes()
    if sha(response) != sent.get('response_sha256'):
        raise ValueError('stored_response_hash_mismatch')
    body = json.loads(response)
    usage = body.get('usage')
    total = usage_total(usage)
    if (total is None or usage != sent.get('provider_usage')
            or usage != sent['ledger'].get('provider_usage')
            or body.get('id') != sent.get('proxy_response_id')
            or 'error' in body or not body.get('choices')
            or body.get('usage_known', True) is not True
            or body.get('usage_bound', 'exact') != 'exact'
            or usage.get('usage_known', True) is not True
            or usage.get('usage_bound', 'exact') != 'exact'):
        raise ValueError('response_usage_not_exact')
    # When available, reject partial/unknown usage flags in the actual call log.
    trial_path = request.parent.parent / 'trial.json'
    if trial_path.exists():
        trial = json.loads(trial_path.read_bytes())
        request_ids = {sent['call_id']}
        request_ids.update(a['request_id'] for a in trial.get('request_archive', [])
                           if a.get('call_id') == sent['call_id'] and a.get('request_id'))
        calls = [c for c in trial['calls'] if c.get('request_id') in request_ids]
        if (trial.get('trial_id') != sent['trial_id'] or len(calls) != 1
                or calls[0]['cost_terms'].get('usage_known') is not True
                or calls[0]['cost_terms'].get('usage_bound') != 'exact'
                or calls[0]['cost_terms'].get('provider_usage') != usage):
            raise ValueError('call_usage_not_exact')
    if total > sent['envelope']['per_upstream_tokens']:
        raise ValueError('upstream_usage_exceeds_reservation')
    if sent.get('wire_error') or sent.get('late') or sent['status'] not in (
            'response_received', 'completion_rejected'):
        raise ValueError('terminal_proxy_response_unresolved')
    return usage


def inspect_window(sent, raw, evidence, window):
    """Recompute assertions from frozen raw bytes, not telemetry's counters."""
    issues = []
    posts, other_requests, retries, errors = [], 0, 0, 0
    zone = ZoneInfo(window['log_timezone'])
    lower, upper = window['lower_epoch_second'], window['upper_epoch_second']
    parsed = []
    offset = evidence['offset']
    for line in raw.splitlines(keepends=True):
        try:
            stamp, message = _line(line, zone)
            parsed.append((stamp, message, offset, offset + len(line)))
        except ValueError:
            issues.append('unparseable_proxy_log_line')
        offset += len(line)
    if (not parsed or parsed[0][0] >= lower or parsed[-1][0] <= upper
            or any(b[0] < a[0] for a, b in zip(parsed, parsed[1:]))
            or not raw.endswith(b'\n')):
        issues.append('proxy_log_window_coverage_missing')
    for stamp, message, start_offset, end_offset in parsed:
        if not lower <= stamp <= upper:
            continue
        http = HTTP.fullmatch(message)
        if http:
            if http[1] == b'POST':
                posts.append({'epoch_second': stamp, 'path': http[2].decode(), 'status': int(http[3]),
                              'offset': start_offset, 'end_offset': end_offset})
            else:
                other_requests += 1
        elif message.startswith(b'transient_429_retry '):
            retries += 1
        elif ERROR.search(message):
            errors += 1
        else:
            issues.append('unknown_proxy_log_event')
    if len(posts) != 1 or posts[0]['path'] != '/v1/chat/completions':
        issues.append('proxy_post_window_not_exclusive')
    if len(posts) == 1 and posts[0]['status'] != 200:
        issues.append('terminal_proxy_response_unresolved')
    attempts = 1 + retries + errors
    if not 1 <= attempts <= sent['reserved_attempts']:
        issues.append('upstream_attempt_count_exceeds_reservation')
    # The original ledger cursor binds the central bytes even if the current
    # log has grown. Padding/boundary lines are also frozen and rehashed.
    cursor = sent.get('proxy_log_window', {})
    try:
        start = cursor['offset'] - evidence['offset']
        end = cursor['end_offset'] - evidence['offset']
        if (cursor.get('available') is not True or evidence['source_path'] != cursor['path']
                or evidence['source_inode'] != cursor['inode']
                or not 0 <= start < end <= len(raw)
                or sha(raw[start:end]) != cursor['sha256']
                or evidence['end_offset'] - evidence['offset'] != len(raw)):
            issues.append('sealed_proxy_log_window_mismatch')
        if len(posts) == 1 and not (cursor['offset'] <= posts[0]['offset']
                                   < posts[0]['end_offset'] <= cursor['end_offset']):
            issues.append('proxy_post_outside_sealed_send_window')
    except (KeyError, TypeError):
        issues.append('sealed_proxy_log_window_missing')
    if sent.get('proxy_source_sha256') != PROXY_SHA256:
        issues.append('unaudited_proxy_source')
    usage = None
    try:
        usage = _usage(sent)
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        issues.append(str(exc) if isinstance(exc, ValueError) else 'durable_response_usage_missing')
    return {'post_count': len(posts), 'posts': posts, 'other_http_request_count': other_requests,
            'retry_line_count': retries, 'error_line_count': errors,
            'actual_upstream_attempts': attempts, 'provider_usage': usage,
            'usage_bound': 'exact' if usage is not None else 'unknown',
            'usage_scope': 'final_proxy_response_only', 'limitation': LIMITATION,
            'issues': sorted(set(issues)), 'complete': not issues}


def verify_telemetry(sent, observed):
    """Independent reconcile path; never fall back to the stronger ID grade."""
    issues = []
    try:
        evidence = observed['evidence']
        raw = Path(evidence['path']).read_bytes()
        if sha(raw) != evidence['sha256']:
            issues.append('proxy_log_evidence_hash_mismatch')
        window = window_spec(sent, observed['window']['log_timezone'])
        if observed['window'] != window:
            issues.append('proxy_log_window_bounds_mismatch')
        actual = inspect_window(sent, raw, evidence, window)
        issues.extend(actual['issues'])
        if any(observed.get(k) != v for k, v in actual.items()):
            issues.append('proxy_log_telemetry_summary_mismatch')
        if observed.get('body_sha256') != sent['body_sha256']:
            issues.append('body_sha256_mismatch')
        if observed.get('proxy_response_id') != sent.get('proxy_response_id'):
            issues.append('proxy_response_id_mismatch')
        if observed.get('proxy_request_id') is not None or observed.get('upstream_attempts') is not None:
            issues.append('ids_forbidden_for_proxy_log_evidence')
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        issues.append('proxy_log_evidence_missing_or_invalid')
    return sorted(set(issues))
