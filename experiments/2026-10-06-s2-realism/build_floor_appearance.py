"""Own-RGB-only fixed appearance references; no evaluation files imported."""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
from harness.zone_solo_cyan_floor_contact import reference_histograms,PARAMS
from harness import vision_loc_protocol as vp
HERE=Path(__file__).resolve().parent

def main(out):
    assert not out.exists()
    cfg=json.loads((HERE/'contact-filter-criteria.json').read_text());raw=Path(cfg['source_raw'])
    frames=[json.loads(s) for s in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    vl=vp.load_vis3()[0];hist_h=np.zeros(256,bool);hist_i=np.zeros(256,bool);sources=[]
    x0,y0,x1,y1=cfg['training']['rectangle_xyxy'];ref=np.zeros((480,640),bool);ref[y0:y1,x0:x1]=True
    for t in cfg['training']['times_sim_s']:
        f=min(frames,key=lambda f:abs(f['sim_time']-t));data=(raw/f['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==f['sha256']
        bgr=cv2.imdecode(np.frombuffer(data,np.uint8),1);hh,ih=reference_histograms(vl.mp.undistort(bgr),ref)
        hist_h|=hh>=PARAMS['hue_count_threshold'];hist_i|=ih>=PARAMS['intensity_count_threshold']
        sources.append(dict(path=str(raw/f['path']),sha256=f['sha256'],t=f['sim_time'],reference_pixels=int(ref.sum()),
            rectangle_xyxy=[x0,y0,x1,y1],hue_histogram=hh.tolist(),intensity_histogram=ih.tolist()))
    table=dict(schema='ugrp.s2.floor_appearance.v1',option='floor_appearance_v1',runtime_gt=False,fit_uses_gt=False,
        parameters=PARAMS,hue_floor_bins=hist_h.tolist(),intensity_floor_bins=hist_i.tolist(),
        training_signal='manually reviewed own RGB floor rectangles; no GT masks or coordinates',
        sources=sources,criteria_sha256=hashlib.sha256((HERE/'contact-filter-criteria.json').read_bytes()).hexdigest(),
        limits='s1050 exploratory calibration; overlapping replay, not held-out validation; real deployment requires field references')
    out.write_text(json.dumps(table,indent=2)+'\n')
if __name__=='__main__':main(Path(sys.argv[1]))
