"""Finite operational supervisor; no wall deadline or automatic retries."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('command_json',type=Path);a=p.parse_args()
    record=json.loads(a.command_json.read_text());codes=[]
    for command in record['commands']:
        result=subprocess.run(command);codes.append(result.returncode)
        if result.returncode:break
    record.update(returncodes=codes,completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    receipt=a.command_json.with_name(a.command_json.stem.replace('-command','-receipt')+'.json')
    receipt.write_text(json.dumps(record,indent=2)+'\n')
    raise SystemExit(codes[-1])
