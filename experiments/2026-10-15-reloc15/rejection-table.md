# reloc15 관문표

서로다른시드·후보·소스는합산하지않음. 누적프레임은독립성공률아님. 정답은GCP평가전용. 상세첫거부·원본은rejection-table.json과round1.json.

|R1 조건|등록→전달→삽입→주행|제어오류|주행오류|종료|
|---|---|---|---|---|
|reloc15-r1-selfmap-93583-candidate-9607de16|149→149→129→0|93/149|0/0|selfmap4_relocalization_exhausted|
|reloc15-r1-selfmap-93584-baseline-9607de16|214→214→131→45|152/214|43/45|cap_end|
|reloc15-r1-selfmap-93584-candidate-9607de16|214→214→132→45|152/214|43/45|cap_end|

|R1 운반|집기→들기→목적지뷰→놓기|held yaw p95/max °|20°초과|종료|
|---|---|---|---|---|
|reloc15-r1-carry-93266-candidate-9607de16|1→1→0→0|7.13/8.81|0/445|cap_end|
|reloc15-r1-carry-93315-baseline-9607de16|1→1→0→0|61.96/67.76|106/696|carry_recovery_setdown_envelope_blocked|
|reloc15-r1-carry-93315-candidate-9607de16|1→1→0→0|25.00/66.47|37/647|carry_recovery_setdown_envelope_blocked|

재현: GCP src/9607de16cfeac0a5ae1308732bab33604b8db7e7에서 PYTHONPATH=. .venv-sim/bin/python /tmp/reloc15-round.py. 원본6개SHA256SUMS전체검증후임대/예약해제. 새판정상수없음.
