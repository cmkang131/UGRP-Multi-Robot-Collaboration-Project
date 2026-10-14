"""Finite Mac-only Gemma relay for robot-private beam tracking skills; Keychain only."""
import argparse,base64,hashlib,json,platform,threading,time,math
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from scripts.openrouter_upstream import keychain_key,http_send,MODEL
from harness.e2e_beam_tracking import SYSTEM

class RelayServer(ThreadingHTTPServer):
    request_queue_size=64  # up to 32 robot clients may arrive at the stage barrier


class Budget:
    # Worst advertised DeepInfra price and entire context window, including image
    # tokens, reserved BEFORE each attempt. Timeout/unknown usage retains reserve.
    reserve_usd=262144*.0000002+768*.0000004
    def __init__(self,root,attempts=600,usd=.30):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.lock=threading.Lock();self.attempts=0;self.charged=0.;self.pending=0.;self.cap_n=attempts;self.cap_usd=usd
        self.save()
    def save(self):
        (self.root/'summary.json').write_text(json.dumps(dict(attempts=self.attempts,charged_or_unknown_reserved_usd=self.charged,
            pending_reserved_usd=self.pending,attempt_cap=self.cap_n,cost_cap_usd=self.cap_usd),indent=2)+'\n')
    def admit(self):
        with self.lock:
            if self.attempts>=self.cap_n or self.charged+self.pending+self.reserve_usd>self.cap_usd:return None
            self.attempts+=1;self.pending+=self.reserve_usd;self.save();return self.attempts
    def finish(self,index,cost,record):
        with self.lock:
            self.pending-=self.reserve_usd;self.charged+=self.reserve_usd if cost is None else cost
            (self.root/f'{index:04d}.json').write_text(json.dumps(record,ensure_ascii=False)+'\n');self.save()

def serve(args):
    if platform.system()!='Darwin':raise ValueError('MAC_KEYCHAIN_RELAY_ONLY')
    if not 0<args.attempts<=600 or not 0<args.usd<=.30 or not 0<args.wall_cap_s<=7200:raise ValueError('FINITE_CAP_REQUIRED')
    key=keychain_key();budget=Budget(args.output,args.attempts,args.usd)
    concurrency=threading.Semaphore(4)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value):
            b=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def do_POST(self):
            if self.path!='/end':return self.reply(404,dict(error='path'))
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=200000:return self.reply(400,dict(error='size'))
            try:
                request=json.loads(self.rfile.read(length))
                if set(request)!={'context','image','image_sha256'}:raise ValueError('FIELDS')
                ctx=request['context'];image=base64.b64decode(request['image'],validate=True)
                if len(image)>100000 or hashlib.sha256(image).hexdigest()!=request['image_sha256']:raise ValueError('IMAGE')
                if set(ctx)!={'schema','robot_id','condition','memory','own_pose','candidates','delivered_text','blocked'} or ctx['schema']!='ugrp.beam_tracking_skill.v1':raise ValueError('CONTEXT_FIELDS')
                if ctx['condition']=='no_comm' and ctx['delivered_text']:raise ValueError('NO_COMM')
                user=json.dumps(ctx,ensure_ascii=False)
                if len(user)>16000:raise ValueError('CONTEXT_SIZE')
            except Exception:return self.reply(400,dict(error='invalid_end_request'))
            concurrency.acquire()
            index=budget.admit()
            if index is None:
                concurrency.release()
                return self.reply(429,dict(error='END_MODEL_BUDGET_EXHAUSTED'))
            record=dict(context=ctx,image_sha256=request['image_sha256'],model=MODEL,provider='deepinfra/turbo',attempt=index);cost=None;started=time.monotonic()
            try:
                payload=dict(model=MODEL,provider=dict(order=['deepinfra/turbo'],allow_fallbacks=False,require_parameters=True),max_tokens=768,temperature=0,
                    response_format=dict(type='json_object'),
                    usage=dict(include=True),messages=[dict(role='system',content=SYSTEM),dict(role='user',content=[dict(type='text',text=user),dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+request['image']))])])
                status,raw,_=http_send(payload,key,timeout=25);response=json.loads(raw);record.update(status=status,response=response)
                usage=response.get('usage',{});v=usage.get('cost')
                if isinstance(v,(int,float)) and math.isfinite(v) and v>=0:cost=float(v)
                elif status==200 and isinstance(usage.get('prompt_tokens'),int) and isinstance(usage.get('completion_tokens'),int):cost=usage['prompt_tokens']*.0000002+usage['completion_tokens']*.0000004
                if status!=200:return self.reply(502,dict(error='MODEL_UPSTREAM',upstream_status=status))
                if response.get('provider')!='DeepInfra' or response.get('model')!=MODEL:return self.reply(502,dict(error='PINNED_PROVIDER_MODEL_MISMATCH'))
                choice=response['choices'][0]
                if choice.get('finish_reason')!='stop':return self.reply(502,dict(error='NON_NORMAL_FINISH'))
                text=choice['message']['content'];decision=json.loads(text)
                return self.reply(200,dict(decision=decision,model=MODEL,attempt=index,cost_usd=cost,usage=usage,wall_s=time.monotonic()-started))
            except Exception as exc:
                record['error_type']=type(exc).__name__
                return self.reply(502,dict(error='MODEL_CALL_FAILED',error_type=type(exc).__name__))
            finally:
                record.update(wall_s=time.monotonic()-started,cost_usd=cost);budget.finish(index,cost,record);concurrency.release()
    server=RelayServer(('127.0.0.1',args.port),Handler)
    timer=threading.Timer(args.wall_cap_s,server.shutdown);timer.daemon=True;timer.start()
    try:server.serve_forever(poll_interval=.2)
    finally:timer.cancel();server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=18093)
    p.add_argument('--attempts',type=int,default=600);p.add_argument('--usd',type=float,default=.30);p.add_argument('--wall-cap-s',type=float,default=3600)
    serve(p.parse_args())
