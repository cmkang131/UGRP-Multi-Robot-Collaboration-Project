"""Restore archived JSON for a deliberate replay, retaining the verified zstd."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    receipts=json.loads((a.root/'delivery-extra-v1/archive-receipts.json').read_text())
    for row in receipts:
        original=a.root/row['original'];compressed=a.root/row['compressed']
        if not original.resolve().is_relative_to(a.root.resolve()):raise ValueError('PATH_ESCAPE')
        if original.exists():
            if hashlib.sha256(original.read_bytes()).hexdigest()!=row['original_sha256']:raise ValueError('EXISTING_FILE_MISMATCH')
            continue
        data=subprocess.check_output(['zstd','-q','-d','-c','--',str(compressed)])
        if hashlib.sha256(data).hexdigest()!=row['original_sha256']:raise ValueError('RESTORE_SHA256_MISMATCH')
        with original.open('xb') as f:f.write(data)


if __name__=='__main__':main()
