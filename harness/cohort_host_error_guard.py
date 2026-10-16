"""Finite-cohort circuit breaker: exactly two consecutive identical host faults.

Mission failure is an outcome, not a host fault. No retry or skipped-row erasure.
"""
import json


class HostErrorGuard:
    def __init__(self):self.key=None;self.count=0

    def observe(self,result):
        if result.get('status')!='HOST_ERROR':self.key=None;self.count=0;return False
        failure=result.get('failure',{})
        key=json.dumps({k:failure.get(k) for k in ('type','message')},sort_keys=True)
        self.count=self.count+1 if self.key==key else 1;self.key=key
        return self.count>=2
