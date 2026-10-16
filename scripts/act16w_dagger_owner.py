"""Private DAgger label RPC. Baseline/student evaluation never launches this."""
import argparse
import base64
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import traceback

from act16w_runtime import require_gcp2, frozen_source
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690/scripts')
from warp_act_api import Owner
from act16w_oracle import OracleBank


class RecordedTrainingOwner(Owner):
    """Save replay poses on the private owner, without changing actor inputs.

    The qualified API skips pose recording on its training lane. DAgger needs
    the same 10 Hz poses as evaluation for retrospective overview playback.
    record_state only appends copies to the existing host-side review journal;
    it never writes integration arrays or supplies a label to the actor.
    """
    def refresh(self, i):
        super().refresh(i)
        if self.training:
            self.hooks.record_state(i, self.tick, self.contexts[i]['world'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true');p.add_argument('--training',action='store_true')
    for k in ('qualified-source','teacher-source','qualification','references','compiled-reference','compiled-geometry','plans','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled or not a.training:p.error('explicit private training opt-in required')
    require_gcp2(training=True);source=frozen_source(Path(__file__).resolve().parents[1])
    protocol=sys.stdout;owner=None;reason='owner_eof'
    def frames():
        result=[]
        for i in range(owner.n):
            obs,jpgs=owner.read_actor(i);result.append(dict(observation=obs,jpegs=[base64.b64encode(x).decode() for x in jpgs]))
        return dict(frames=result,terminal=(~owner.active).tolist())
    try:
        with redirect_stdout(sys.stderr):
            owner=RecordedTrainingOwner(json.loads(a.plans.read_text())['episodes'],a.out,qualified_source=a.qualified_source,teacher_source=a.teacher_source,
                qualification=a.qualification,references=json.loads(a.references.read_text()),compiled_reference=a.compiled_reference,compiled_geometry=a.compiled_geometry,enabled=True,training=True)
            bank=OracleBank(owner);owner.write('dagger-source.json',dict(source_sha=source,baseline_owner='0362037280c6cbc4677f70366db43b9892b23690',teacher_library='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8',teacher_actions_executed=0,replay_pose_hz=10,replay_pose_scope='host-side review journal only'))
        print(json.dumps(frames()),file=protocol,flush=True)
        for line in sys.stdin:
            request=json.loads(line)
            if set(request)=={'close'}:reason=str(request['close']);break
            with redirect_stdout(sys.stderr):
                if set(request)=={'actions'}:owner.step(request['actions']);response=frames()
                elif set(request)=={'instruct','skill'}:owner.instruct(request['instruct'],request['skill']);response=frames()
                elif set(request)=={'oracle_student_selected_commands'}:
                    labels,audit=bank.query(request['oracle_student_selected_commands']);response=dict(oracle_labels=labels,audit=audit)
                else:raise ValueError('private DAgger request whitelist mismatch')
            print(json.dumps(response,allow_nan=False),file=protocol,flush=True)
    except BaseException as error:
        reason='HOST_ERROR'
        if a.out.exists():owner.write('HOST_ERROR.json',dict(status='HOST_ERROR',reason=repr(error),traceback=traceback.format_exc())) if owner else (a.out/'HOST_ERROR.json').write_text(traceback.format_exc())
        raise
    finally:
        if owner is not None:
            with redirect_stdout(sys.stderr):owner.close(reason)


if __name__=='__main__':main()
