"""Opt-in metadata-zone restoration; original launcher, host guard and policy stay on disk unchanged."""
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys
from urllib.request import Request, ProxyHandler, build_opener

# User 2026-10-27 03:45 KST explicitly authorized snapshot restoration to another
# L4 zone as infrastructure only. These values are the actual restored VM from
# infra-ready.json / GCE metadata, not a wider project/machine approval.
EXPECTED = ('ugrp-sim-f-1016', 'ugrp-act-l4-gcp6', 'g2-standard-8', 'asia-northeast1-c')
EXPECTED_INSTANCE_ID = '2102818194467198298'
ORIGINAL_HOST_SHA256 = '9a91cd2bd7ef010e818080dac0cb725decc47b8be00e209a8edffc696809812d'
HOST_FILE = Path('/home/ugrp/ugrp-sim/src/beamact5-tools/gcp6_host.py')
PACKAGE = Path('/home/ugrp/ugrp-sim/baseline-treatment')


def main():
    if hashlib.sha256(HOST_FILE.read_bytes()).hexdigest() != ORIGINAL_HOST_SHA256:
        raise ValueError('original host-guard bytes mismatch')
    spec = importlib.util.spec_from_file_location('gcp6_host', HOST_FILE)
    host = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(host)
    original = host.APPROVED_HOSTS['gcp6']
    if original[:4] != (*EXPECTED[:3], 'asia-northeast3-a'):
        raise ValueError('original gcp6 approval unexpectedly changed')
    request = Request('http://169.254.169.254/computeMetadata/v1/instance/id',
                      headers={'Metadata-Flavor': 'Google'})
    with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
        instance_id = response.read(4096).decode().strip()
    if instance_id != EXPECTED_INSTANCE_ID:
        raise ValueError('restore adapter is limited to the actual approved VM id')
    # Replace only the gcp6 row's zone in this process. Retain the original
    # Linux/project/instance/machine/account validation function verbatim.
    host.APPROVED_HOSTS['gcp6'] = (*EXPECTED, original[4])
    identity = host.gcp6_identity()
    if tuple(identity[k] for k in ('project_id', 'instance', 'machine_type', 'zone')) != EXPECTED:
        raise ValueError('restored host identity mismatch')
    sys.modules['gcp6_host'] = host
    record = dict(schema='ugrp.baseline.host-zone-restore.v1',
                  instance_id=instance_id, observed=identity,
                  original_host_module_sha256=ORIGINAL_HOST_SHA256,
                  original_approved_zone='asia-northeast3-a', restored_zone=EXPECTED[3],
                  frozen_files_modified=False, policy_or_physics_changed=False)
    if sys.argv[1:] == ['--check']:
        print(json.dumps(record, indent=2))
        return
    args = sys.argv[1:]
    out = Path(args[args.index('--out') + 1])
    with (out.parent / (out.name + '.host-zone-restore.json')).open('x') as stream:
        json.dump(record, stream, indent=2)
    # Execute the original future_driver by its original path: its HERE, loader
    # hashes, treatment AST, argv, seeds, model, cadence and evaluator stay fixed.
    sys.path.insert(0, str(PACKAGE))
    driver = PACKAGE / 'future_driver.py'
    sys.argv = [str(driver), *args]
    runpy.run_path(str(driver), run_name='__main__')


if __name__ == '__main__':
    main()
