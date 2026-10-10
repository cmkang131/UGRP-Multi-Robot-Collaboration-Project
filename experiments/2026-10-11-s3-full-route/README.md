# s3fix23: unbroken registered routes (DEV)
- v175; oracle-x86 OSMesa LP4; 3 routes × 2 fixed seeds, all concurrently; 2/3 legs have 170/240 SIM s, wall cap 3600 s.
- Raw diagnosis: 109 frames, 88 FOV-clipped (right both seeds/r1+r2 and three s14206/r2); 21 fully inside; clipped motor pulses 0.
- Detector support 8952–9354 pixels, band 3560–4018; no scalar confidence; thresholds unchanged. GT projection is evaluation only.
- Default-off candidates: baseline left; canonical inspect/pan1500 right; canonical + <=2 calibrated reverse pulses on fresh clipped RGB for three-leg.
- Same routes/seeds; route-assigned exploration cannot rank candidates causally. Registration freezes commands and criteria before new execution.
- Criteria: each held transport >=20mm, each corner <=20mm; final settled floor release; drop/tilt/HOST zero; horizon is incomplete.
- Move-settle-look follows [Weiss1987 p407](https://www.cs.cmu.edu/~lew/PUBLICATION%20PDFs/VISUAL%20SERVOING/JRA%201987.pdf).
- Persistent raw ~/ugrp-sim/runs; initial 180-second checks and immediate full retrieval; source fixed after green related tests.
- Scope: unbroken staged alignment-to-final-release route, not the original dock-to-B mission; results pending in summary.json.
