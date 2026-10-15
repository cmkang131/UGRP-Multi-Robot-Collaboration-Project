"""Native student-camera recording of the qualified beampair7 CPU teacher."""
import argparse
from pathlib import Path
from harness.grasp_act_data import read_json, write_json
from harness.beampair_recording import gate_proof, make_training_view
from scripts.run_beampair1 import run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--episode',type=int,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--dependency-root',type=Path,required=True)
    a=p.parse_args();root=Path('/home/ugrp/ugrp-sim');proof=gate_proof(root)
    report=run(read_json(a.plan)['episodes'][a.episode],a.out,a.dependency_root,
        mode='beampair1_v1',candidate='baseline',cap_s=60,rendezvous='peer_rendezvous_v2',
        approach_repair='beampair_approach_v2',wall_layer='beampair_wall_clear_v1',
        peer_yield='beampair_peer_yield_v1',failure_tail=True,record_training=True,recording_proof=proof)
    admission=make_training_view(a.out.parent)
    write_json(a.out.parent/'recording-admission.json',admission)
    (a.out.parent/'SOURCE_SHA').write_text(admission.get('path') and read_json(Path(admission['path'])/'result.json')['source_sha'] or '')


if __name__=='__main__':main()
