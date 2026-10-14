"""UTC communication and bounded scheduling; never reads physics or actuators."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import math
import os
import socket
import struct
import subprocess
import time

SCHEMA='ugrp.utc.reservation.v1'
SERVER='time.cloudflare.com'
NTP_EPOCH=2208988800

class ClockError(RuntimeError): pass

def iso_utc(value: float) -> str:
    return datetime.fromtimestamp(value,timezone.utc).isoformat()

def parse_utc(value) -> float:
    if isinstance(value,str):
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp.tzinfo is None: raise ClockError('UTC timestamp requires timezone')
        value=stamp.timestamp()
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ClockError('Invalid UTC timestamp')
    return float(value)

def decode_ntp(data,request,t1,t4,elapsed):
    if len(data)<48 or data[0]&7!=4 or data[0]>>6==3 or not 1<=data[1]<=15:
        raise ClockError('Invalid or unsynchronized NTP server')
    if data[24:32]!=request[40:48]: raise ClockError('NTP origin mismatch')
    if abs((t4-t1)-elapsed)>.005: raise ClockError('Clock changed during NTP sample')
    def stamp(pos):
        a,b=struct.unpack('!II',data[pos:pos+8]);return a-NTP_EPOCH+b/2**32
    t2,t3=stamp(32),stamp(40)
    delay=elapsed-(t3-t2)
    if t3<t2 or delay<-.001: raise ClockError('Inconsistent NTP timestamps')
    root_delay=struct.unpack('!i',data[4:8])[0]/65536
    root_dispersion=struct.unpack('!I',data[8:12])[0]/65536
    offset=((t2-t1)+(t3-t4))/2
    return {'offset_s':offset,'round_trip_s':max(0,delay),
            'estimated_error_s':max(0,delay)/2+max(0,root_delay)/2+root_dispersion,
            'receive_utc_s':t4,'stratum':data[1]}

class NtpUtcClock:
    """NTP UTC anchored to monotonic time; leaves the PC system clock untouched."""
    def __init__(self,server=SERVER,*,max_age_s=300,drift_budget_ppm=100):
        self.server=server;self.max_age_s=max_age_s;self.drift_budget_ppm=drift_budget_ppm
        self.anchor=None;self.samples=[]
    def synchronize(self,count=3,timeout_s=3):
        if not 1<=count<=8: raise ClockError('Invalid NTP startup sample count')
        samples=[]
        for index in range(count):
            try:
                addr=socket.getaddrinfo(self.server,123,socket.AF_INET,socket.SOCK_DGRAM)[0][4]
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                    sock.settimeout(timeout_s);sock.connect(addr)
                    req=bytearray(48);req[0]=0x23
                    t1=time.time();m1=time.monotonic();v=t1+NTP_EPOCH
                    req[40:48]=struct.pack('!II',int(v),int((v%1)*2**32))
                    sock.send(req);data=sock.recv(512);m4=time.monotonic();t4=time.time()
                    sample=decode_ntp(data,req,t1,t4,m4-m1)
                    sample.update(monotonic_s=m4,server_address=addr[0]);samples.append(sample)
            except (OSError,ClockError) as exc:
                self.samples.append({'error':str(exc)})
            if index+1<count: time.sleep(.4)  # finite startup burst, not continuous public polling
        self.samples.extend(samples)
        if not samples: raise ClockError('No valid public NTP response')
        self.anchor=min(samples,key=lambda s:s['round_trip_s'])
        return self.health()
    def monotonic(self): return time.monotonic()
    def now(self):
        if self.anchor is None: raise ClockError('NTP clock was not initialized')
        age=self.monotonic()-self.anchor['monotonic_s']
        if age>self.max_age_s: raise ClockError('NTP clock evidence expired; refresh before reservation')
        return self.anchor['receive_utc_s']+self.anchor['offset_s']+age
    def health(self):
        self.now();age=self.monotonic()-self.anchor['monotonic_s']
        return {'source':'ntp','server':self.server,'server_address':self.anchor['server_address'],
                'synchronized':True,'age_s':age,'estimated_error_ms':1000*(self.anchor['estimated_error_s']+age*self.drift_budget_ppm/1e6),
                'error_is_estimate':True,'system_clock_changed':False,'max_age_s':self.max_age_s,
                'wait_drift_budget_ppm':self.drift_budget_ppm}

class SystemUtcClock:
    """Robot clock maintained by chrony; readiness is rechecked for each reservation."""
    def __init__(self,*,require_public=True,max_sync_age_s=600):
        self.require_public=require_public;self.max_sync_age_s=max_sync_age_s
    def monotonic(self): return time.monotonic()
    def now(self): return time.time()
    def health(self):
        try:
            p=subprocess.run(['chronyc','-n','tracking'],capture_output=True,text=True,timeout=5,env={**os.environ,'LC_ALL':'C'})
            fields={line.split(':',1)[0].strip():line.split(':',1)[1].strip() for line in p.stdout.splitlines() if ':' in line}
            address=fields.get('Reference ID','').split('(')[-1].rstrip(')')
            sync=p.returncode==0 and fields.get('Leap status')=='Normal'
            if self.require_public: sync=sync and ipaddress.ip_address(address).is_global
            ref=datetime.strptime(fields['Ref time (UTC)'],'%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc).timestamp()
            age=self.now()-ref
            error=abs(float(fields['System time'].split()[0]))+float(fields['Root delay'].split()[0])/2+float(fields['Root dispersion'].split()[0])
            sync=sync and -2<=age<=self.max_sync_age_s
            return {'source':'chrony','server_address':address,'synchronized':bool(sync),
                    'age_s':age,'estimated_error_ms':max(0,error)*1000,'error_is_estimate':True,
                    'max_age_s':self.max_sync_age_s,'wait_drift_budget_ppm':100}
        except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
            raise ClockError('Chrony evidence unavailable: '+str(exc)) from exc

def require_ready(clock,max_error_ms=250):
    info=clock.health()
    if not info.get('synchronized'): raise ClockError('Clock not synchronized to public NTP')
    if not math.isfinite(info['estimated_error_ms']) or info['estimated_error_ms']>max_error_ms: raise ClockError('Clock estimate exceeds configured budget')
    return info

def wait_until_utc(target,*,clock,max_lateness_ms=20,max_clock_shift_ms=20,max_error_ms=250,cancelled=None):
    target=parse_utc(target);health=require_ready(clock,max_error_ms)
    # UTC for agreement, monotonic for all local waits. Never use a SIM tick here.
    anchor_mono=clock.monotonic();anchor_utc=clock.now();delay=target-anchor_utc
    if not 0<delay<=300: raise ClockError('Reservation is past or too far in the future')
    deadline=anchor_mono+delay
    while True:
        if cancelled is not None and cancelled(): raise ClockError('Reservation cancelled or coordinator disconnected')
        current_mono=clock.monotonic();current_utc=clock.now()
        shift=current_utc-(anchor_utc+current_mono-anchor_mono)
        if abs(shift)*1000>max_clock_shift_ms: raise ClockError('Clock jump invalidated reservation')
        remaining=deadline-current_mono
        if remaining<=0: break
        time.sleep(min(.01,remaining))
    late=(current_mono-deadline)*1000
    if late>max_lateness_ms: raise ClockError('Missed reserved execution window')
    # No process launches or NTP network round trips at the execution deadline.
    elapsed=clock.monotonic()-anchor_mono
    health={**health,'age_s':health['age_s']+elapsed,
            'estimated_error_ms':health['estimated_error_ms']+elapsed*health.get('wait_drift_budget_ppm',100)/1000}
    if health['age_s']>health.get('max_age_s',600): raise ClockError('Clock evidence expired during wait')
    if health['estimated_error_ms']>max_error_ms: raise ClockError('Clock estimate exceeded budget during wait')
    return {'execute_at_utc_s':target,'execute_at_utc':iso_utc(target),
            'issued_at_utc_s':clock.now(),'issued_at_monotonic_s':clock.monotonic(),
            'local_wait_lateness_ms':late,'clock_health':health}

@dataclass
class Reservation:
    participant: str
    clock: object
    max_error_ms: float=250
    prepared: dict|None=None
    consumed: bool=False
    def prepare(self,message):
        if self.prepared is not None: raise ClockError('Duplicate preparation')
        if message.get('schema')!=SCHEMA or message.get('phase')!='PREPARE': raise ClockError('Invalid prepare schema')
        participants=message.get('participants')
        if (not isinstance(participants,list) or not participants or any(not isinstance(p,str) or not p for p in participants)
                or len(participants)!=len(set(participants)) or self.participant not in participants):
            raise ClockError('Invalid participants')
        action_id=message.get('action_id')
        if not isinstance(action_id,str) or not action_id or len(action_id)>128: raise ClockError('Invalid action ID')
        target=parse_utc(message.get('execute_at_utc_s'))
        if not .5<=target-self.clock.now()<=300: raise ClockError('Insufficient reservation lead time')
        health=require_ready(self.clock,self.max_error_ms)
        self.prepared={'action_id':action_id,'participants':list(participants),'execute_at_utc_s':target}
        return {'phase':'READY','participant':self.participant,**self.prepared,'clock_health':health,'utc_s':self.clock.now()}
    def commit(self,message,callback,*,cancelled=None):
        if self.prepared is None or self.consumed: raise ClockError('Unprepared or duplicate commit')
        if message.get('schema')!=SCHEMA or message.get('phase')!='COMMIT': raise ClockError('Invalid commit schema')
        if any(message.get(k)!=v for k,v in self.prepared.items()): raise ClockError('Reservation identity changed')
        if set(message.get('ready_participants',[]))!=set(self.prepared['participants']): raise ClockError('Missing participant readiness')
        self.consumed=True
        timing=wait_until_utc(self.prepared['execute_at_utc_s'],clock=self.clock,max_error_ms=self.max_error_ms,cancelled=cancelled)
        result=callback()
        return {'phase':'FIRED','participant':self.participant,'action_id':self.prepared['action_id'],**timing,'result':result}

def scheduled_request(command):
    children=command.get('commands')
    if isinstance(children,list) and children:
        timed=[c for c in children if isinstance(c,dict) and 'execute_at_utc_s' in c]
        if timed:
            if len(timed)!=len(children): raise ClockError('Mixed timed/untimed parallel group')
            if any(not isinstance(c.get('id'),str) or not c['id'] for c in timed) or len({c['id'] for c in timed})!=len(timed):
                raise ClockError('Parallel reservations require unique command IDs')
            times={parse_utc(c['execute_at_utc_s']) for c in timed}
            if len(times)!=1: raise ClockError('Parallel reservations have different UTC times')
            target=times.pop()
            if 'execute_at_utc_s' in command and parse_utc(command['execute_at_utc_s'])!=target:
                raise ClockError('Parent and child UTC reservation mismatch')
            budgets=[c.get('clock_budget_ms') for c in timed]
            if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=250 for v in budgets):
                raise ClockError('Each scheduled participant requires an explicit clock budget')
            return {**command,'execute_at_utc_s':target,'clock_budget_ms':min(budgets)}
    return command if 'execute_at_utc_s' in command else None

def command_deadline(command,*,clock=None):
    """Shared REAL/SIM dispatcher hook. Physics time stays independent of UTC."""
    command=scheduled_request(command)
    if command is None: return None
    if not isinstance(command.get('id'),str) or not command['id']: raise ClockError('Scheduled command requires ID')
    budget=command.get('clock_budget_ms')
    if type(budget) not in (int,float) or not math.isfinite(budget) or not 0<budget<=250:
        raise ClockError('Scheduled action requires an explicit clock_budget_ms in (0, 250]')
    return wait_until_utc(command['execute_at_utc_s'],clock=clock or SystemUtcClock(),
                          max_error_ms=float(budget))
