# pairact P5 eval stack (-p5)

PAIRACT_R1_EVAL_PREREG v2 P5 execution stack. Only difference from -c5:
adapter candidate pairact_p5_eval (r13_detour + carry_cap_s 120).

| tree | branch | SHA |
|---|---|---|
| teacher | dsh/pairact-p2-carrypath-c5 | 75929e7719ad98a089e3dda5251f4249d8bae511 (unchanged) |
| adapter | dsh/pairact-p2-carrypath-a-p5 | afd7a6e17c6501d308b6a1d9015b15f5d5da9ed4 |
| root | dsh/pairact-p2-carrypath-r-p5 | this commit |

carry_cap_s 120 comes from the eval prereg episode cap rule (60 s grasp cap
+ carry_budget computed from the P2 teacher smoke carry times, max 120).
Existing candidates are unchanged.
