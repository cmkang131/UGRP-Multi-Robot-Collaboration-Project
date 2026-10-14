import unittest
from harness.rgb_communication_runtime import TraceRecorder,MessageChannel,RuntimeLimits,_IdFactory,_ActorState

class UTCTransportTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.ids=_IdFactory()
        self.trace=TraceRecorder(run_id='utc',condition='natural',wall_clock=lambda:0.,wall_started_s=0.,path=None,ids=self.ids,utc_clock=lambda:self.now)
        self.channel=MessageChannel('natural',['a','b'],RuntimeLimits(),self.trace,self.ids)
    def send(self):
        return self.channel.send('a',{'recipients':['b'],'content':'prepare','ttl_s':2.},decision_id='d',clock_time_s=0.,trace_sim_time_s=0.,tick_index=0,actor=_ActorState('a'))
    def test_ntp_send_receive_timestamps(self):
        self.send();self.now+=1
        rows,expired=self.channel.receive('b',clock_time_s=0.,trace_sim_time_s=0.,tick_index=1)
        self.assertEqual(len(rows),1);self.assertFalse(expired)
        self.assertEqual(rows[0]['sent_at_utc_s'],1000)
        self.assertEqual(rows[0]['received_at_utc_s'],1001)
    def test_message_expires_even_when_sim_time_is_stopped(self):
        self.send();self.now+=3
        rows,expired=self.channel.receive('b',clock_time_s=0.,trace_sim_time_s=0.,tick_index=1)
        self.assertFalse(rows);self.assertEqual(len(expired),1)

if __name__=='__main__':unittest.main()
