"""Opt-in private L4 inference; the serialized student capability is unchanged.

Batch size stays one, with a serialized deterministic CUDA forward. Request
arrival order / batch composition must not change the action under load.
No simulator, evaluator, teacher, or model-provider credential is accepted.
"""
import base64
import ipaddress
import json
from pathlib import Path
import threading
from urllib.parse import urlparse
import urllib.request

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import sha256, write_json


def private_url(url):
    parsed=urlparse(url)
    if (parsed.scheme!='http' or parsed.username or parsed.password or parsed.path not in ('','/')
            or parsed.query or parsed.fragment or not ipaddress.ip_address(parsed.hostname).is_private):
        raise ValueError('literal private-IP HTTP endpoint required')
    return url.rstrip('/')


def decode_request(request):
    if set(request)!={'observation','jpegs'}:raise ValueError('worker request whitelist mismatch')
    c.validate_observation(request['observation'])
    if len(request['jpegs'])!=c.RGB_HISTORY:raise ValueError('exact own RGB history required')
    return request['observation'],[base64.b64decode(s,validate=True) for s in request['jpegs']]


class RemoteActor:
    def __init__(self,model,url):
        self.url=private_url(url)
        with urllib.request.urlopen(self.url+'/health',timeout=120) as response:
            self.health=json.load(response)
        if (self.health.get('ready') is not True or self.health.get('batch_size')!=1
                or self.health.get('deterministic_cuda') is not True
                or self.health.get('model_sha256')!=sha256(Path(model)/'model.safetensors')
                or self.health.get('contract_sha256')!=sha256(Path(c.__file__))):
            raise ValueError('remote model/contract/deterministic batch identity mismatch')

    def predict_request(self,request):
        decode_request(request)
        call=urllib.request.Request(self.url+'/predict',data=json.dumps(request,allow_nan=False).encode(),
                                    headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(call,timeout=120) as response:result=json.load(response)
        if set(result)!={'chunk'}:raise ValueError('remote response whitelist mismatch')
        values=np.asarray(result['chunk'])
        if values.shape!=(c.CHUNK,c.ACTION_DIM) or not np.isfinite(values).all():raise ValueError('invalid remote chunk')
        return values.tolist()


def serve(model,bind,port,report_path):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from harness.grasp_act_policy import GraspActor,observation_batch
    from scripts.grasp_act_training_guard import require_gcp,source_sha
    host,source=require_gcp(training=True),source_sha()
    if not ipaddress.ip_address(bind).is_private:raise ValueError('private bind required')
    import torch
    torch.backends.cudnn.benchmark=False
    torch.backends.cudnn.deterministic=True
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False
    actor=GraspActor.load(model,device='cuda')
    lock=threading.Lock()
    report={'ready':True,'host':host,'source_sha':source,'model_sha256':sha256(Path(model)/'model.safetensors'),
            'contract_sha256':sha256(Path(c.__file__)),'batch_size':1,'deterministic_cuda':True,
            'requests':0,'errors':0,'teacher_fields':0,'max_wall_s':7*3600}
    write_json(report_path,report)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,status,value):
            body=json.dumps(value,allow_nan=False).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            self.respond(200,report) if self.path=='/health' else self.respond(404,{'error':'unknown path'})
        def do_POST(self):
            if self.path!='/predict':self.respond(404,{'error':'unknown path'});return
            try:
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                observation,jpegs=decode_request(request)
                # JPEG checks/resize happen concurrently on the CPU. Only the
                # same batch-one CUDA forward is serialized, independently of
                # concurrency and SIM/wall timing.
                batch=observation_batch(observation,jpegs,actor.stats,blank=actor.blank)
                with lock:
                    batch={k:torch.from_numpy(v.copy()).unsqueeze(0).to('cuda') for k,v in batch.items()}
                    with torch.inference_mode():values=actor.policy.predict_action_chunk(batch)[0].cpu().numpy()
                    values=actor.decode_predictions(values)
                    if values.shape!=(c.CHUNK,c.ACTION_DIM) or not np.isfinite(values).all():raise ValueError('invalid CUDA chunk')
                    report['requests']+=1
                    if report['requests']%100==0:write_json(report_path,report)
                self.respond(200,{'chunk':values.tolist()})
            except Exception as exc:
                with lock:report['errors']+=1;write_json(report_path,report)
                self.respond(400,{'error':type(exc).__name__+': '+str(exc)})
    server=ThreadingHTTPServer((bind,port),Handler)
    # Same <=7h process resource budget as the trainer; VM keeps its 8h STOP.
    timer=threading.Timer(7*3600,server.shutdown);timer.daemon=True;timer.start()
    try:server.serve_forever()
    finally:timer.cancel();server.server_close();report['ready']=False;write_json(report_path,report)
