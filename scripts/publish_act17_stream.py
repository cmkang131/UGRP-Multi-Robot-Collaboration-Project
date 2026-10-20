"""Mac memory relay of registered ACT17 ZIP streams; never forward credentials."""
import argparse
from datetime import datetime,timezone
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import platform
import shlex
import subprocess
from urllib.parse import quote

REPO='cmkang131/UGRP-Multi-Robot-Collaboration-Project'
TAG='models-20261017-act17-v7-r1'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    p.add_argument('--host',required=True);p.add_argument('--key',type=Path,required=True)
    p.add_argument('--entry',required=True);p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args()
    if not a.enabled or platform.system()!='Darwin':p.error('explicit Mac memory relay only')
    ipaddress.ip_address(a.host)
    if a.receipt.exists():raise FileExistsError('inspect existing receipt; never retry overwrite')
    ssh=['ssh','-o','BatchMode=yes','-o','ForwardAgent=no','-i',str(a.key),'ugrp@'+a.host]
    entry=json.loads(subprocess.check_output([*ssh,'cat '+shlex.quote(a.entry)]))
    if (entry.get('schema')!='ugrp.act17.stream_package.v1' or entry['release']['tag']!=TAG or
            entry['candidate'] not in ['M','F','S'] or not entry['id'].startswith('act17-v7-native-r1-') or
            not entry['staging'].startswith('/home/ugrp/ugrp-sim/runs/act17-v7/') or
            len(entry['packaging_source_sha'])!=40):raise ValueError('registered v7 package mismatch')
    asset=entry['release']['asset'];size=entry['archive']['bytes'];expected=entry['archive']['sha256']
    if Path(asset).name!=asset or not asset.endswith('.zip'):raise ValueError('immutable simple ZIP asset name required')
    release=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/releases/tags/{TAG}']))
    if release.get('draft') or any(r['name']==asset for r in release['assets']):raise ValueError('public Release and unused asset name required')
    source='/home/ugrp/ugrp-sim/src/'+entry['packaging_source_sha']+'/scripts/package_act17_model.py'
    remote=shlex.join(['/home/ugrp/ugrp-rl1b-act-env/bin/python',source,'--enabled','--stream',a.entry])
    token=subprocess.check_output(['gh','auth','token','--hostname','github.com'],stderr=subprocess.PIPE).decode().strip()
    connection=http.client.HTTPSConnection('uploads.github.com',timeout=60);proc=None
    try:
        connection.putrequest('POST',f'/repos/{REPO}/releases/{release["id"]}/assets?name={quote(asset)}')
        for key,value in [('Authorization','Bearer '+token),('Accept','application/vnd.github+json'),('Content-Type','application/zip'),('Content-Length',str(size))]:connection.putheader(key,value)
        connection.endheaders();token=None
        proc=subprocess.Popen([*ssh,remote],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        digest=hashlib.sha256();count=0
        while block:=proc.stdout.read(65536):
            digest.update(block);count+=len(block)
            if count>size:raise ValueError('stream exceeds registered size')
            connection.send(block)
        proc.wait()
        if proc.returncode or count!=size or digest.hexdigest()!=expected:raise ValueError('stream hash/size/exit mismatch; inspect public asset')
        response=connection.getresponse();body=response.read()
        if response.status!=201:raise RuntimeError('GitHub upload HTTP '+str(response.status))
        result=json.loads(body)
        if result['size']!=size or result['name']!=asset:raise ValueError('uploaded metadata differs')
        receipt=dict(status='uploaded_public_verification_pending',utc=datetime.now(timezone.utc).isoformat(),id=entry['id'],
            url=result['browser_download_url'],asset_id=result['id'],bytes=size,sha256=expected,stream_hash_verified=True,
            Mac_archive_written=False,VM_archive_written=False,VM_credentials_forwarded=False,public_redownload_verified=False,loading_verified=False)
        with a.receipt.open('x') as f:json.dump(receipt,f,indent=2)
        print(json.dumps(receipt))
    finally:
        token=None;connection.close()
        if proc and proc.poll() is None:proc.terminate();proc.wait()


if __name__=='__main__':main()
