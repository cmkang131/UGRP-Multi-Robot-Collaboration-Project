|load|N|status|SIM s|physics GPU s|render GPU s|render CPU s|control Python s|H2D alloc/copy s|D2H blocking s|D2H GB|explicit wait s|numpy calls|
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|exclusive_ugrp-act-l4-gcp4|1|PROFILE_COMPLETE|0.300000|6.166545|0.065491|0.380661|0.562194|0.014102|0.152915|0.484735|0.548440|577|
|exclusive_ugrp-act-l4-gcp4|4|PROFILE_COMPLETE|0.300000|7.327180|0.132699|1.472151|0.924020|0.016037|0.493475|1.947535|0.719591|1711|
|exclusive_ugrp-act-l4-gcp4|16|PROFILE_COMPLETE|0.300000|10.857424|0.418326|6.748103|2.577608|0.020284|3.378441|7.931691|2.071587|6247|
|exclusive_ugrp-act-l4-gcp4|64|HOST_ERROR|—|—|—|—|—|—|—|—|—|—|

Shared gcp2 warp7 R3 (별도 코호트): N16·2그룹·0.4 SIM s / loop145.099 s; command+physics97.792 s, render+평가복사35.126 s. 분리 계측 없음.

intrusive CUDA event intervals and host phase timings; columns overlap, not additive; no task success evidence
