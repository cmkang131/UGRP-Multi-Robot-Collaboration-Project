import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
source=Path(__file__).with_name('utc_clock.py')
if not source.exists():source=Path(__file__).resolve().parents[1]/'harness'/'utc_clock.py'
import sys
spec=importlib.util.spec_from_file_location('clock',source);clock=importlib.util.module_from_spec(spec);sys.modules['clock']=clock;spec.loader.exec_module(clock)

class FakeClock:
    def __init__(self):self.m=0.;self.jump=0.;self.info={'synchronized':True,'estimated_error_ms':5,'age_s':1,'source':'ntp'}
    def now(self):return 1000+self.m+self.jump
    def monotonic(self):return self.m
    def health(self):return dict(self.info)
    def sleep(self,v):self.m+=v

def prepare(c):
    r=clock.Reservation('a',c)
    p={'schema':clock.SCHEMA,'phase':'PREPARE','action_id':'same-action','participants':['a','b'],'execute_at_utc_s':1001.}
    r.prepare(p)
    return r,{**p,'phase':'COMMIT','ready_participants':['a','b']}

class UTCClockTests(unittest.TestCase):
    def test_high_resolution_monotonic_source(self):
        with patch.object(clock.time,'perf_counter',return_value=12.3456789):
            self.assertEqual(clock.NtpUtcClock().monotonic(),12.3456789)
    def test_timezone_required(self):
        with self.assertRaises(clock.ClockError):clock.parse_utc('2026-10-14T13:04:30')
        self.assertEqual(clock.parse_utc('2026-10-14T13:04:30+09:00'),clock.parse_utc('2026-10-14T04:04:30Z'))
    def test_actual_callback_waits_monotonic(self):
        c=FakeClock();r,p=prepare(c);calls=[]
        with patch.object(clock.time,'sleep',c.sleep): result=r.commit(p,lambda:calls.append(c.monotonic()))
        self.assertEqual(len(calls),1);self.assertGreaterEqual(calls[0],1)
        self.assertLess(result['local_wait_lateness_ms'],1)
    def test_duplicate_commit_rejected(self):
        c=FakeClock();r,p=prepare(c)
        with patch.object(clock.time,'sleep',c.sleep):r.commit(p,lambda:None)
        with self.assertRaises(clock.ClockError):r.commit(p,lambda:None)
    def test_missing_peer_ready(self):
        c=FakeClock();r,p=prepare(c);p['ready_participants']=['a']
        with self.assertRaises(clock.ClockError):r.commit(p,lambda:self.fail('callback ran'))
    def test_changed_timestamp(self):
        c=FakeClock();r,p=prepare(c);p['execute_at_utc_s']+=1
        with self.assertRaises(clock.ClockError):r.commit(p,lambda:self.fail('callback ran'))
    def test_clock_jump_aborts(self):
        c=FakeClock();r,p=prepare(c)
        def sleep(v):c.sleep(v);c.jump=.1
        with patch.object(clock.time,'sleep',sleep),self.assertRaises(clock.ClockError):r.commit(p,lambda:self.fail('callback ran'))
    def test_late_wakeup_aborts(self):
        c=FakeClock();r,p=prepare(c)
        def sleep(v):c.sleep(v+2)
        with patch.object(clock.time,'sleep',sleep),self.assertRaises(clock.ClockError):r.commit(p,lambda:self.fail('callback ran'))
    def test_bad_clock_budget_rejected(self):
        c=FakeClock();c.info['estimated_error_ms']=300
        with self.assertRaises(clock.ClockError):prepare(c)
    def test_unsynchronized_clock_rejected(self):
        c=FakeClock();c.info['synchronized']=False
        with self.assertRaises(clock.ClockError):prepare(c)
    def test_legacy_command_not_delayed(self):
        class NeverClock:
            def health(self):raise AssertionError('legacy command queried clock')
        self.assertIsNone(clock.command_deadline({'id':'x'},clock=NeverClock()))
    def test_invalid_ntp_origin(self):
        data=bytearray(48);data[0]=0x24;data[1]=3
        req=bytearray(48);req[40:48]=b'12345678'
        with self.assertRaises(clock.ClockError):clock.decode_ntp(data,req,100,100.02,.02)
    def test_cancellation_aborts(self):
        c=FakeClock();r,p=prepare(c)
        with self.assertRaises(clock.ClockError):r.commit(p,lambda:self.fail('callback ran'),cancelled=lambda:True)
    def test_explicit_action_budget_required(self):
        with self.assertRaises(clock.ClockError):clock.command_deadline({'id':'x','execute_at_utc_s':1001},clock=FakeClock())
    def test_parallel_reservation_is_preserved(self):
        group={'id':'group','commands':[{'id':'a','execute_at_utc_s':1001,'clock_budget_ms':50},{'id':'b','execute_at_utc_s':1001,'clock_budget_ms':100}]}
        request=clock.scheduled_request(group)
        self.assertEqual(request['execute_at_utc_s'],1001)
        self.assertEqual(request['clock_budget_ms'],50)
    def test_mismatched_parallel_time_rejected(self):
        group={'id':'group','commands':[{'id':'a','execute_at_utc_s':1001,'clock_budget_ms':50},{'id':'b','execute_at_utc_s':1002,'clock_budget_ms':50}]}
        with self.assertRaises(clock.ClockError):clock.scheduled_request(group)
    def test_malformed_parallel_id_rejected(self):
        group={'id':'group','commands':[{'id':[],'execute_at_utc_s':1001,'clock_budget_ms':50}]}
        with self.assertRaises(clock.ClockError):clock.scheduled_request(group)
    def test_budget_exhaustion_during_wait_aborts(self):
        c=FakeClock();c.info['estimated_error_ms']=249.99;r,p=prepare(c)
        with patch.object(clock.time,'sleep',c.sleep),self.assertRaises(clock.ClockError):r.commit(p,lambda:self.fail('callback ran'))
    def test_nonfinite_uncertainty_rejected(self):
        c=FakeClock();c.info['estimated_error_ms']=float('nan')
        with self.assertRaises(clock.ClockError):prepare(c)
    def test_ntp_network_uncertainty_is_recorded(self):
        req=bytearray(48);req[40:48]=b'12345678'
        data=bytearray(48);data[0]=0x24;data[1]=3;data[24:32]=req[40:48]
        for pos,t in [(32,100.015),(40,100.016)]:
            v=t+clock.NTP_EPOCH;data[pos:pos+8]=struct.pack('!II',int(v),int((v%1)*2**32))
        result=clock.decode_ntp(data,req,100,100.021,.021)
        self.assertAlmostEqual(result['offset_s'],.005,places=6)
        self.assertAlmostEqual(result['estimated_error_s'],.01,places=6)

if __name__=='__main__':unittest.main()
