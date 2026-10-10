# s3fix23: unbroken registered routes (DEV)
- v175 / ca3d51b7; oracle-x86 OSMesa LP4; six frozen cases concurrently; 2/3 legs have 170/240 SIM s, wall cap 3600 s.
- Before: 109 post-release frames, 88 FOV-clipped (last-frame corners 7-32px below viewport), 21 visible; clipped motor pulses 0; GT projection evaluation only.
- Default-off candidates: left existing baseline, right canonical inspect/pan1500, three-leg canonical + <=2 calibrated reverse/fresh-look pulses; no threshold/seed changes.
- Results: held transport 6/6 -> 3/6 -> 1/2; corners <=20mm 6/6 -> 2/6 -> 0/2; final settled release 2/6, all-criteria route success 0/6.
- Final released errors 27.298/20.534mm; HOST/tilt 0; LOAD_DROP guards 3, all grounded (2.943N, z15.892mm, vz near zero), actual free fall unobserved; clipped horizon 1.
- Reentry joint hover 5/6; one existing reverse pulse predicted12.917mm/actual11.136mm recovered clipped r2; right pan-only one seed remained 1113/1113 clipped per robot.
- Six originals immediately retrieved: 41088 raw + 53 metadata hashes matched; paths/sha256 and vector error decomposition in summary.json; first55s command bytes 12/12 unchanged.
- [Weiss1987 p407](https://www.cs.cmu.edu/~lew/PUBLICATION%20PDFs/VISUAL%20SERVOING/JRA%201987.pdf) move-settle-look; [W3C state lifecycle](https://www.w3.org/TR/scxml/#onentry) informs next release-epoch fix; implementation inference only.
- Scope: uninterrupted staged alignment-to-final-release, route-assigned exploration; next: release-latch lifecycle, backoff expansion, 22-26mm next-leg start displacement. PR416 draft.
