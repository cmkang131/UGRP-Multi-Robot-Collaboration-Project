"""Relay one staged native model from owned L4 memory to an existing Release.

Run on Mac only. Credentials remain in local process memory; no model archive
is written on Mac, no credential is forwarded to SSH, and assets are immutable.
Public re-download/full hashes/loading are separate required delivery steps.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import platform
import shlex
import subprocess
from urllib.parse import quote

SSH=['ssh','-o','BatchMode=yes','-o','ProxyCommand=none','-o','HostName=34.64.52.225','gcp2']
REPO='cmkang131/UGRP-Multi-Robot-Collaboration-Project'
TAG='models-20261016-act16w-native-v1'


def api(path):
    return json.loads(subprocess.check_output(['gh','api',path]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true');p.add_argument('--arm',choices=['A','B','C','D1'],required=True)
    p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    if not a.enabled or platform.system()!='Darwin':p.error('explicit local Mac memory relay only')
    if a.receipt.exists():raise FileExistsError('receipt already exists; inspect before retry')
    folder=f'/home/ugrp/ugrp-sim/runs/act16w-native-experiment-r1/model-{a.arm}'
    entry=json.loads(subprocess.check_output([*SSH,'cat '+shlex.quote(folder+'/registry-entry.pending.json')]))
    asset=entry['release']['asset'];size=entry['archive']['bytes'];expected=entry['archive']['sha256']
    if (entry['release']['tag']!=TAG or entry['id']!=f'act16w-native-v1-{a.arm.lower()}-step10000-20261016'
            or not asset.endswith('.zip') or '/' in asset):raise ValueError('registered native model mismatch')
    release=api(f'repos/{REPO}/releases/tags/{TAG}')
    if release.get('draft'):raise ValueError('public Release required')
    if any(row['name']==asset for row in release['assets']):
        raise FileExistsError('asset already exists; never overwrite; verify existing public asset instead')
    token=subprocess.check_output(['gh','auth','token','--hostname','github.com'],stderr=subprocess.PIPE).decode().strip()
    conn=http.client.HTTPSConnection('uploads.github.com',timeout=60)
    proc=None
    try:
        conn.putrequest('POST',f'/repos/{REPO}/releases/{release["id"]}/assets?name={quote(asset)}')
        conn.putheader('Authorization','Bearer '+token)
        conn.putheader('Accept','application/vnd.github+json')
        conn.putheader('Content-Type','application/zip');conn.putheader('Content-Length',str(size));conn.endheaders()
        token=None
        proc=subprocess.Popen([*SSH,'cat '+shlex.quote(folder+'/'+asset)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        digest=hashlib.sha256();count=0
        while block:=proc.stdout.read(65536):
            count+=len(block)
            if count>size:raise ValueError('remote archive exceeds registered size')
            digest.update(block);conn.send(block)
        proc.wait()
        if proc.returncode or count!=size or digest.hexdigest()!=expected:
            raise ValueError('remote stream hash/length/exit mismatch; public verification required before delivery')
        response=conn.getresponse();body=response.read()
        if response.status!=201:raise RuntimeError(f'GitHub upload HTTP {response.status}; no delivery claim')
        result=json.loads(body)
        if result['name']!=asset or result['size']!=size:raise ValueError('GitHub asset metadata mismatch')
        receipt=dict(status='uploaded_public_verification_pending',utc=datetime.now(timezone.utc).isoformat(),
            arm=a.arm,release_tag=TAG,asset_id=result['id'],url=result['browser_download_url'],bytes=size,
            sha256=expected,stream_hash_verified=True,Mac_archive_written=False,VM_credentials_forwarded=False,
            public_redownload_verified=False,loading_verified=False)
        with a.receipt.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
        print(json.dumps(receipt))
    finally:
        token=None;conn.close()
        if proc and proc.poll() is None:proc.terminate();proc.wait()


if __name__=='__main__':main()
