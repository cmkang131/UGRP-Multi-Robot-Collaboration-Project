import importlib.util
from pathlib import Path
import struct
import unittest

source=Path(__file__).with_name('clock_pair_probe.py')
if not source.exists(): source=Path(__file__).resolve().parents[1]/'scripts'/'clock_pair_probe.py'
spec=importlib.util.spec_from_file_location('probe',source)
probe=importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)

def packet(t2,t3):
    req=bytearray(48); req[40:48]=b'12345678'
    data=bytearray(48); data[0]=0x24; data[1]=3; data[24:32]=req[40:48]
    for pos,v in [(32,t2),(40,t3)]:
        stamp=v+probe.EPOCH; data[pos:pos+8]=struct.pack('!II',int(stamp),int((stamp%1)*2**32))
    return bytes(data),bytes(req)

class ClockProbeTests(unittest.TestCase):
    def test_symmetric_path_offset_sign_and_delay(self):
        data,req=packet(100.015,100.016)
        row=probe.decode_response(data,req,100,100.021,.021)
        self.assertAlmostEqual(row['offset_ms'],5,places=3)
        self.assertAlmostEqual(row['round_trip_ms'],20,places=3)
        self.assertAlmostEqual(row['network_uncertainty_ms'],10,places=3)
    def test_origin_validation(self):
        data,req=packet(100.015,100.016)
        with self.assertRaisesRegex(ValueError,'origin'): probe.decode_response(data,b'\0'*48,100,100.021,.021)
    def test_unsynchronized_server(self):
        data,req=packet(100.015,100.016); data=bytes([data[0]|0xc0])+data[1:]
        with self.assertRaises(ValueError): probe.decode_response(data,req,100,100.021,.021)
    def test_wall_clock_jump(self):
        data,req=packet(100.015,100.016)
        with self.assertRaisesRegex(ValueError,'clock changed'): probe.decode_response(data,req,100,101.021,.021)
    def test_network_uncertainty_rejects_nominally_zero_offset(self):
        rows=[{'offset_ms':0,'round_trip_ms':80,'network_uncertainty_ms':40}]*30
        self.assertFalse(probe.summarize(rows,20)['sampled_clock_check_passed'])
    def test_loss_rejects_sample_check(self):
        good={'offset_ms':1,'round_trip_ms':2,'network_uncertainty_ms':1}
        self.assertFalse(probe.summarize([good]*20+[{'error':'timeout'}]*10,20)['sampled_clock_check_passed'])
    def test_clock_budget_pass(self):
        rows=[{'offset_ms':1,'round_trip_ms':2,'network_uncertainty_ms':1}]*30
        self.assertTrue(probe.summarize(rows,20)['sampled_clock_check_passed'])

if __name__=='__main__': unittest.main()
