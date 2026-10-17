import unittest
from harness.rgb_communication_runtime import TraceRecorder,MessageChannel,RuntimeLimits,_IdFactory,_ActorState,_expire_actor_messages,run_rgb_communication_ntp
from unittest.mock import patch

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
    def test_delivered_message_expires_when_sim_time_stops(self):
        self.send();self.now+=1
        rows,_=self.channel.receive('b',clock_time_s=0.,trace_sim_time_s=0.,tick_index=1)
        actor=_ActorState('b');actor.received_messages=rows;self.now+=2
        _expire_actor_messages(actor,clock_time_s=0.,trace_sim_time_s=0.,trace=self.trace)
        self.assertFalse(actor.received_messages);self.assertEqual(len(actor.expired_messages),1)
    def test_async_ntp_profile_passes_utc_source(self):
        with patch('harness.utc_clock.NtpUtcClock') as c, patch('harness.rgb_communication_runtime.run_rgb_communication_async') as run:
            run_rgb_communication_ntp(object(),{},asynchronous=True)
            c.return_value.synchronize.assert_called_once()
            self.assertIs(run.call_args.kwargs['communication_utc_clock'],c.return_value.now)
    def test_message_expires_even_when_sim_time_is_stopped(self):
        self.send();self.now+=3
        rows,expired=self.channel.receive('b',clock_time_s=0.,trace_sim_time_s=0.,tick_index=1)
        self.assertFalse(rows);self.assertEqual(len(expired),1)

if __name__=='__main__':unittest.main()
