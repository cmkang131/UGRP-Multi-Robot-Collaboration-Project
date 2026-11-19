#!/usr/bin/env python3
"""Hand event marker for real trials, until the laptop runner writes events.jsonl itself.

    python3 scripts/real_event_mark.py runs/<trial>/events.jsonl --robot r1 --item red_1

Type a letter and Enter; each line gets the laptop monotonic time (the clock of real_overhead.py record):
  s start   h handover   r release_done   f finished   q quit
For release, the sign number can follow: `r 12`.
"""
import argparse
import json
import time

KEYS = {'s': 'start', 'h': 'handover', 'r': 'release_done', 'f': 'finished'}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('out'); p.add_argument('--robot', default='r1'); p.add_argument('--item')
    a = p.parse_args()
    with open(a.out, 'a') as f:
        while True:
            parts = input('> ').split()
            t = time.monotonic()
            if not parts or parts[0] == 'q':
                break
            if parts[0] not in KEYS:
                print('s h r f q'); continue
            row = {'t': round(t, 4), 'event': KEYS[parts[0]], 'source': 'hand'}
            if row['event'] != 'start':
                row['robot'] = a.robot
            if row['event'] in ('handover', 'release_done') and a.item:
                row['item'] = a.item
            if row['event'] == 'release_done' and len(parts) > 1:
                row['sign'] = int(parts[1])
            f.write(json.dumps(row) + '\n'); f.flush()
            print(row)
