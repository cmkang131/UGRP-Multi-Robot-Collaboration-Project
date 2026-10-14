"""Read-only NTP comparison on the follower. Records UTC and monotonic time."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import socket
import statistics
import struct
import subprocess
import time
from datetime import datetime, timezone

EPOCH = 2208988800

def decode_response(data, request, t1, t4, elapsed):
    if len(data) < 48 or data[0] & 7 != 4 or data[0] >> 6 == 3 or not 1 <= data[1] <= 15:
        raise ValueError('Invalid or unsynchronized NTP response')
    if data[24:32] != request[40:48]:
        raise ValueError('Response origin does not match request')
    if abs((t4-t1)-elapsed) > .005:
        raise ValueError('Wall clock changed during request')
    def stamp(pos):
        a, b = struct.unpack('!II', data[pos:pos+8])
        return a - EPOCH + b / 2**32
    t2, t3 = stamp(32), stamp(40)
    delay = elapsed-(t3-t2)
    if t3 < t2 or delay < -.001:
        raise ValueError('Inconsistent NTP timestamps')
    offset = ((t2-t1)+(t3-t4))/2
    return {'t1_client_send_utc_s':t1,'t2_server_receive_utc_s':t2,
            't3_server_send_utc_s':t3,'t4_client_receive_utc_s':t4,
            'offset_ms':offset*1000,'round_trip_ms':max(0,delay)*1000,
            'network_uncertainty_ms':max(0,delay)*500,'stratum':data[1]}

def sample(server):
    row = {'utc':datetime.now(timezone.utc).isoformat(),'monotonic_ns':time.monotonic_ns()}
    try:
        addr = socket.getaddrinfo(server,123,socket.AF_INET,socket.SOCK_DGRAM)[0][4]
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(2); sock.connect(addr)
            req = bytearray(48); req[0] = 0x23
            t1=time.time(); m1=time.monotonic()
            v=t1+EPOCH; req[40:48]=struct.pack('!II',int(v),int((v%1)*2**32))
            sock.send(req); data=sock.recv(512)
            m4=time.monotonic(); t4=time.time()
            row.update(decode_response(data,req,t1,t4,m4-m1))
            row['server_address']=addr[0]
    except (OSError,ValueError) as exc:
        row['error']=str(exc)
    return row

def summarize(rows, budget_ms):
    good=[r for r in rows if 'offset_ms' in r]
    result={'requested_samples':len(rows),'valid_samples':len(good),
            'offset_sign':'leader minus follower; positive = follower behind',
            'provisional_clock_budget_ms':budget_ms,'sampled_clock_check_passed':False,
            'limitations':'Network delay asymmetry remains. This is a sampled clock check, not a guarantee of future clock or physical actuation accuracy.'}
    if good:
        offsets=[r['offset_ms'] for r in good]
        bounds=sorted(abs(r['offset_ms'])+r['network_uncertainty_ms'] for r in good)
        result.update(offset_median_ms=statistics.median(offsets),offset_min_ms=min(offsets),
                      offset_max_ms=max(offsets),offset_stddev_ms=statistics.stdev(offsets) if len(good)>1 else 0,
                      round_trip_median_ms=statistics.median(r['round_trip_ms'] for r in good),
                      sampled_relative_error_estimate_p95_ms=bounds[math.ceil(.95*len(bounds))-1],
                      sampled_relative_error_estimate_max_ms=max(bounds))
        result['sampled_clock_check_passed']=(len(good)>=.9*len(rows) and
            result['sampled_relative_error_estimate_max_ms']<=budget_ms)
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--server',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--count',type=int,default=30)
    parser.add_argument('--budget-ms',type=float,default=20)
    args=parser.parse_args()
    if not 5<=args.count<=300 or args.budget_ms<=0: parser.error('Invalid count or budget')
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'pair_samples.csv').exists(): raise SystemExit('Refusing to overwrite prior samples')
    rows=[]; due=time.monotonic()
    for index in range(args.count):
        time.sleep(max(0,due-time.monotonic()))
        row=sample(args.server); row['sample']=index+1; rows.append(row)
        print(json.dumps(row),flush=True); due=time.monotonic()+1
    keys=sorted(set().union(*(r.keys() for r in rows)))
    path=args.output/'pair_samples.csv'
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys); writer.writeheader(); writer.writerows(rows)
    result=summarize(rows,args.budget_ms)
    result.update(leader_address=args.server,follower_host=socket.gethostname(),robot_motion_commands=0,
                  utc=datetime.now(timezone.utc).isoformat(),monotonic_ns=time.monotonic_ns(),
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  samples_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    for name, command in [('tracking',['chronyc','-n','tracking']),('sources',['chronyc','-n','sources','-v'])]:
        p=subprocess.run(command,capture_output=True,text=True,timeout=10)
        (args.output/('probe_'+name+'.txt')).write_text(p.stdout+p.stderr)
        if p.returncode: result['sampled_clock_check_passed']=False
        if name=='tracking' and not any(line.startswith('Leap status') and line.split(':',1)[1].strip()=='Normal' for line in p.stdout.splitlines()):
            result['sampled_clock_check_passed']=False
        if name=='sources' and not any(line.startswith('^*') and line.split()[1]==args.server for line in p.stdout.splitlines()):
            result['sampled_clock_check_passed']=False
    (args.output/'pair_result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['sampled_clock_check_passed'] else 3

if __name__=='__main__': raise SystemExit(main())
