"""Authenticated-SSH reservation agent. Default callback writes a marker only."""
import argparse
import json
from pathlib import Path
import socket
import sys
import queue
import threading
if (Path(__file__).resolve().parents[1]/'harness').is_dir():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from harness.utc_clock import ClockError,Reservation,SystemUtcClock,require_ready
except ModuleNotFoundError:
    from utc_clock import ClockError,Reservation,SystemUtcClock,require_ready

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--participant',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    clock=SystemUtcClock();reservation=Reservation(args.participant,clock)
    incoming=queue.Queue();cancelled=threading.Event()
    def read_input():
        try:
            for line in sys.stdin:
                value=json.loads(line)
                if value.get('phase')=='ABORT':cancelled.set()
                incoming.put(value)
        finally:
            cancelled.set();incoming.put({'phase':'ABORT'})
    threading.Thread(target=read_input,daemon=True).start()
    def emit(value):
        value['host']=socket.gethostname()
        with (args.output/'events.jsonl').open('a') as f:f.write(json.dumps(value)+'\n')
        print(json.dumps(value),flush=True)
    try:
        emit({'phase':'WELCOME','participant':args.participant,'utc_s':clock.now(),'clock_health':require_ready(clock),'robot_motion_commands':0})
        while True:
            message=incoming.get()
            if message.get('phase')=='ABORT': emit({'phase':'ABORTED','robot_motion_commands':0});return 0
            if message.get('phase')=='PREPARE': emit(reservation.prepare(message))
            elif message.get('phase')=='COMMIT':
                emit(reservation.commit(message,lambda:{'marker_only':True,'robot_motion_commands':0},cancelled=cancelled.is_set));return 0
            else: raise ClockError('Unknown phase')
        raise ClockError('Coordinator disconnected; no action performed')
    except Exception as exc:
        emit({'phase':'ERROR','error':str(exc),'robot_motion_commands':0});return 1

if __name__=='__main__':raise SystemExit(main())
