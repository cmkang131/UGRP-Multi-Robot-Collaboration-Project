"""Finite Mac relay: stream one GCP2 archive to a new GitHub Release.

Authentication stays in Mac process memory. No model archive is stored on Mac,
and no credential is sent to the VM. Existing assets are never overwritten.
"""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import shlex
import subprocess
from urllib.parse import quote, urlsplit


REPO = 'cmkang131/UGRP-Multi-Robot-Collaboration-Project'
HERE = Path(__file__).resolve().parent


def api(arguments, payload=None):
    command = ['gh', 'api', *arguments]
    if payload is not None:
        command += ['--input', '-']
    return json.loads(subprocess.check_output(command, input=None if payload is None else json.dumps(payload).encode()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm', choices=('C1', 'C2'), required=True)
    p.add_argument('--target-sha', required=True)
    a = p.parse_args()
    entry = json.loads((HERE / (a.arm + '-model-entry.json')).read_text())
    tag = entry['release']['tag']
    expected_tag = 'models-20261016-beamact3c-' + a.arm.lower() + '-v1'
    if tag != expected_tag:
        raise ValueError('exact new arm Release required')
    # Creating a new tag/Release is explicit in the user's preservation request.
    # Do not modify any existing Release, including a draft from another actor.
    release = api(['repos/' + REPO + '/releases', '--method', 'POST'], dict(
        tag_name=tag, target_commitish=a.target_sha, draft=True,
        name='beamact3 ' + a.arm + ' fixed step20000 comparison model',
        body='Fixed final step20000 ACT comparison model. ' + '; '.join(entry['limitations']) +
             '. See model-entry.json and bundled provenance for hashes, source and evaluation scope.'))
    upload = urlsplit(release['upload_url'].split('{')[0])
    token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
    remote = '/home/ugrp/ugrp-sim/ops-reviews/beamact3c/' + a.arm + '/release-v1/'
    names = [entry['release']['asset'], 'model-entry.json', 'SHA256SUMS']
    receipts = []
    for name in names:
        if name.endswith('.zip'):
            size = entry['archive']['bytes']; expected = entry['archive']['sha256']
            local = None
        else:
            local = (HERE / (a.arm + '-' + name)).read_bytes()
            size = len(local); expected = hashlib.sha256(local).hexdigest()
        connection = http.client.HTTPSConnection(upload.hostname, timeout=120)
        connection.putrequest('POST', upload.path + '?name=' + quote(name))
        for k, v in {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'User-Agent': 'UGRP-beamact3c-model-relay', 'Content-Type': 'application/octet-stream',
                     'Content-Length': str(size)}.items():
            connection.putheader(k, v)
        connection.endheaders()
        digest = hashlib.sha256(); count = 0
        if local is None:
            # Own finite lease prevents a cooperative idle stop during streaming.
            code = ('import datetime,json,os,pathlib,sys;'
                    'p=pathlib.Path(' + repr('/home/ugrp/ugrp-sim/leases/beamact3c-' + a.arm + '-upload.json') + ');'
                    'p.open("x").write(json.dumps(dict(task="beamact3c-model-upload",pid=os.getpid(),'
                    'start=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end="finite archive stream",concurrency=0)));'
                    '\ntry:\n with open(' + repr(remote + name) + ',"rb") as f:\n'
                    '  while b:=f.read(1024*1024):sys.stdout.buffer.write(b)\n'
                    'finally:p.unlink()\n')
            process = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', 'gcp2',
                                        'python3 -c ' + shlex.quote(code)], stdout=subprocess.PIPE)
            while block := process.stdout.read(1024 * 1024):
                connection.send(block); digest.update(block); count += len(block)
            if process.wait() != 0:
                raise RuntimeError('GCP2 archive stream failed')
        else:
            connection.send(local); digest.update(local); count = len(local)
        if count != size or digest.hexdigest() != expected:
            raise ValueError('stream bytes/hash mismatch')
        response = connection.getresponse(); body = response.read(); status = response.status
        connection.close()
        if status != 201:
            raise RuntimeError('GitHub upload failed: ' + str(status) + ' ' + body.decode()[:1000])
        asset = json.loads(body)
        if asset['size'] != size or asset.get('digest') != 'sha256:' + expected:
            raise ValueError('GitHub asset digest/size mismatch')
        receipts.append({k: asset.get(k) for k in ('id', 'name', 'state', 'size', 'digest', 'browser_download_url')})
        (HERE / (a.arm + '-release-upload.json')).write_text(json.dumps(dict(
            release_id=release['id'], tag=tag, assets=receipts, published=False), indent=2) + '\n')
    published = api(['repos/' + REPO + '/releases/' + str(release['id']), '--method', 'PATCH'], {'draft': False})
    record = dict(release_id=release['id'], tag=tag, assets=receipts, published=not published['draft'],
                  url=published['html_url'], target_commitish=a.target_sha,
                  archive_stored_on_mac=False, credentials_on_vm=False, redownload_verified=False)
    (HERE / (a.arm + '-release-upload.json')).write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
