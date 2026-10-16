"""Mac relay only. Jev credential is read once into relay memory, never argv/logs."""
import json
import hashlib
from pathlib import Path
import platform
import subprocess
import threading
from harness.model_http import post
from harness.jev_decider_eval import JEV_URL
from harness.e2e_jev_decider import transform


class Jev:
    def __init__(self,root,*,key=None,send=post):
        if key is None:
            if platform.system()!='Darwin':raise ValueError('MAC_KEYCHAIN_RELAY_ONLY')
            r=subprocess.run(['security','find-generic-password','-s','ugrp.typesafe.ai','-a','jev','-w'],capture_output=True,timeout=15)
            if r.returncode or not r.stdout.strip():raise ValueError('JEV_KEYCHAIN_UNAVAILABLE')
            key=r.stdout.decode().strip()
        self._key=key;self.send=send;self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.Lock()

    def complete(self,request,response,call_id):
        def select(body):
            result=self.send(body,JEV_URL,self._key,30)
            # model_http scrubs response text; keep an additional recursive wire scrub.
            result=json.loads(json.dumps(result).replace(self._key,'[REDACTED_SECRET]'))
            row=dict(call_id=call_id,request=body,result=result)
            with self.lock,(self.root/'calls.jsonl').open('a') as f:
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
            return result
        return transform(request,response,select)
