"""Camera-only wall search when close occluders make one view ambiguous.

Own image/verifier feedback only. A completed sweep is never wall confirmation.
The three folded arm postures reuse existing PR405 hardware presets.
"""
from dataclasses import dataclass

POSTURES={
 'ahead':{1:2000,3:858,4:2320,5:1320},
 'up':{1:2000,3:960,4:2410,5:1215},
 'down':{1:2000,3:740,4:2320,5:1320},
}

@dataclass(frozen=True)
class View:
    posture:str
    pan:int

    def commands(self):
        return {**POSTURES[self.posture],6:self.pan}


class WallCameraSearch:
    """Try above/below an occluder, then sweep both sides at all three heights.

    `confirmed` must come from the independent wall verifier. Edge count,
    colour and having exhausted the search never substitute for that evidence.
    """
    def __init__(self, start_pan=1500, *, pans=(500,750,1000,1250,1500,1750,2000,2250,2500), max_views=30):
        if not 500<=start_pan<=2500 or not 1<=max_views<=40:raise ValueError('Invalid camera search bounds')
        if any(not isinstance(v,int) or not 500<=v<=2500 for v in pans):raise ValueError('Invalid pan')
        self.start_pan=start_pan;self.max_views=max_views;self.visited=[];self.done=False
        first=[View(p,start_pan) for p in ('up','down','ahead')]
        self.candidates=first+[View(p,pan) for p in ('up','ahead','down') for pan in (sorted(set(pans)) if p!='ahead' else sorted(set(pans),reverse=True))]

    def next_view(self, *, confirmed=False, observed_floor_support=0):
        if self.done:return None
        if confirmed and observed_floor_support>=3:self.done=True;return None
        if len(self.visited)>=self.max_views:self.done=True;return None
        for view in self.candidates:
            if view not in self.visited:
                self.visited.append(view);return view
        self.done=True;return None


def bounded_pan_steps(current,target,max_step=250):
    if not(500<=current<=2500 and 500<=target<=2500 and 1<=max_step<=250):raise ValueError('Invalid pan transition')
    result=[]
    while current!=target:
        current+=max(-max_step,min(max_step,target-current));result.append(current)
    return result
