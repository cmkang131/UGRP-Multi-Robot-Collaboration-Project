"""Mac-only d1 credential boundary, used by replay and the existing S4 relay."""
import copy
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import threading

from harness.model_http import post
from harness import e2e_dialogue_decider as protocol
from harness.llm_completion import assess_completion, normal_completion
from harness.three_robot_plan import parse

URL = 'https://api.liquid.ai/decisions/v1/systemone'


class Speech:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def write_message(self, request, call_id, selected, speak):
        user, _ = protocol.unpack(request)
        speech = protocol.speech_request(request, selected)
        # Even without a channel the same protocol choice is made; no invented peer.
        needs_speech = (user['condition'] != 'no_comm' and user['channel'].get('encoding') != 'schema'
                        and user['channel']['can_send_to']
                        and user.get('dialogue_window', {}).get('your_utterances_left', 1) > 0)
        gemma = speak(speech) if needs_speech else None
        with self.lock, (self.root / 'speech.jsonl').open('a') as f:
            f.write(json.dumps(dict(call_id=call_id, selected=selected, request=speech,
                response=gemma), ensure_ascii=False) + '\n')
        text = ''
        if gemma is not None:
            if not normal_completion(assess_completion(gemma, study_json=False)):
                raise ValueError('NORMAL_GEMMA_SPEECH_REQUIRED')
            value = parse(gemma['choices'][0]['message']['content'])
            if not isinstance(value, dict) or set(value) != {'text'}:
                raise ValueError('GEMMA_SPEECH_ONLY_SCHEMA_REQUIRED')
            text = value['text']
        assembled = protocol.assemble(user, selected, text)
        response = copy.deepcopy(gemma) if gemma is not None else dict(
            model=request.get('model'), choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', content=''))],
            usage=dict(prompt_tokens=0, completion_tokens=0, total_tokens=0))
        response['choices'][0]['message']['content'] = json.dumps(assembled, ensure_ascii=False)
        response['ugrp_dialogue_speech'] = dict(gemma_message=text, gemma_called=bool(gemma), action_immutable=True)
        return response


class Code(Speech):
    """Contract state machine; construction and selection never access a key/model."""
    def complete(self, request, call_id, speak):
        import time
        user, _ = protocol.unpack(request)
        if user.get('dialogue_decider') != protocol.CODE_MODE:
            raise ValueError('CODE_DIALOGUE_MODE_REQUIRED')
        started = time.perf_counter()
        selected = protocol.code_select(user)
        elapsed = time.perf_counter() - started
        response = self.write_message(request, call_id, selected, speak)
        response['ugrp_code_dialogue'] = dict(mode=protocol.CODE_MODE, selected=selected,
            latency_s=elapsed, decision_model_calls=0, decision_cost_usd=0,
            **response['ugrp_dialogue_speech'])
        return response


class D1(Speech):
    def __init__(self, root, *, key=None, send=post):
        if key is None:
            if platform.system() != 'Darwin':
                raise ValueError('D1_MAC_KEYCHAIN_ONLY')
            r = subprocess.run(['security', 'find-generic-password', '-s', 'ugrp-liquid-d1', '-a', 'd1', '-w'],
                               capture_output=True, timeout=15)
            if r.returncode or not r.stdout.strip():
                raise ValueError('D1_KEYCHAIN_UNAVAILABLE')
            key = r.stdout.decode().strip()
        self._key = key; self.send = send; self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True); self.lock = threading.Lock()

    def select(self, body, call_id):
        result = self.send(body, URL, self._key, 30)
        result = json.loads(json.dumps(result).replace(self._key, '[REDACTED_SECRET]'))
        # Full image stays in the original request. Text + image hash in audit.
        audit = copy.deepcopy(body)
        audit['images'] = [{'data_url_sha256': hashlib.sha256(s.encode()).hexdigest()} for s in body['images']]
        with self.lock, (self.root / 'calls.jsonl').open('a') as f:
            f.write(json.dumps(dict(call_id=call_id, request=audit, result=result), ensure_ascii=False) + '\n')
        return result

    def complete(self, request, call_id, speak):
        """d1 first, then message-only Gemma. No failed stage is silently retried."""
        oreq = protocol.observation_request(request)
        observed = self.select(oreq, call_id+':vision')
        if observed.get('status') != 'ok':
            raise ValueError('D1_VISUAL_UPSTREAM_FAILURE')
        observation = protocol.parse_decision(observed['body'], oreq)
        dreq = protocol.decision_request(request, observation)
        result = self.select(dreq, call_id+':action')
        if result.get('status') != 'ok':
            raise ValueError('D1_UPSTREAM_FAILURE')
        selected = {**observation, **protocol.parse_decision(result['body'], dreq)}
        response = self.write_message(request, call_id, selected, speak)
        response['ugrp_d1_dialogue'] = dict(mode=protocol.MODE, selected=selected,
            latency_s=observed['latency_s']+result['latency_s'],
            vision_latency_s=observed['latency_s'],action_latency_s=result['latency_s'],
            usage=result['body'].get('usage'), response=result['body'],
            vision_usage=observed['body'].get('usage'),vision_response=observed['body'],
            request_sha256=hashlib.sha256(json.dumps(dreq, sort_keys=True).encode()).hexdigest(),
            **response['ugrp_dialogue_speech'])
        return response
