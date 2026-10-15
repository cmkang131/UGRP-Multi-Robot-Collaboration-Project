# reloc15 관문표 — NOT_READY

기본off·원본GCP평가전용. 같은시드짝비교외소스/조건/시간구간을합산하지않는다. 프레임분모는독립성공률아님. 3라운드18회 종료, 후속큐미제출.

|실행|등록→전달→삽입→주행|제어오류|주행오류|종료|
|---|---|---|---|---|
|reloc15-r1-selfmap-93583-candidate-9607de16|149→149→129→0|93/149|0/0|selfmap4_relocalization_exhausted|
|reloc15-r1-selfmap-93584-baseline-9607de16|214→214→131→45|152/214|43/45|cap_end|
|reloc15-r1-selfmap-93584-candidate-9607de16|214→214→132→45|152/214|43/45|cap_end|
|reloc15-r2-selfmap-93583-candidate-44ba1bc6|219→219→154→33|91/219|29/33|cap_end|
|reloc15-r2-selfmap-93584-baseline-44ba1bc6|214→214→132→45|152/214|43/45|cap_end|
|reloc15-r2-selfmap-93584-candidate-44ba1bc6|216→216→209→45|73/216|6/45|cap_end|
|reloc15-r3-selfmap-93571-candidate-e44b4987|217→217→206→84|88/217|24/84|cap_end|
|reloc15-r3-selfmap-93583-baseline-e44b4987|149→149→129→0|93/149|0/0|selfmap4_relocalization_exhausted|
|reloc15-r3-selfmap-93585-candidate-e44b4987|216→216→170→64|146/216|53/64|cap_end|

|운반실행|본pickup→align→lift→구역뷰→release|held yaw p95/max °|20°초과|종료|
|---|---|---|---|---|
|reloc15-r1-carry-93266-candidate-9607de16|1→1→1→0→0|7.08/8.81|0/464|cap_end|
|reloc15-r1-carry-93315-baseline-9607de16|1→1→1→0→0|61.94/67.76|106/715|carry_recovery_setdown_envelope_blocked|
|reloc15-r1-carry-93315-candidate-9607de16|1→1→1→0→0|23.72/66.47|37/666|carry_recovery_setdown_envelope_blocked|
|reloc15-r2-carry-93266-candidate-e44b4987|1→1→1→0→0|42.16/92.98|16/156|supervisor_stop|
|reloc15-r2-carry-93315-baseline-e44b4987|1→0→0→0→0|N/A (held sample0)|0/0|supervisor_stop|
|reloc15-r2-carry-93315-candidate-e44b4987|1→1→1→0→0|69.03/94.91|13/170|supervisor_stop|
|reloc15-r3-carry-93266-candidate-1d7d5b26|1→1→1→0→0|32.42/36.09|48/242|supervisor_stop|
|reloc15-r3-carry-93313-candidate-1d7d5b26|1→1→1→0→0|14.76/15.80|0/229|supervisor_stop|
|reloc15-r3-carry-93315-candidate-1d7d5b26|1→1→1→0→0|17.20/18.48|0/348|supervisor_stop|

R1–R3自己지도buffer의control frame_id소비결함을최종코드에서고쳤지만새물리0. 운반held평가는finger contact+바닥보다높음으로통일(5cm임의경계사용안함). 0명령yaw비는undefined, 원본미가용은성공0으로대체하지않는다.

재현: GCP의해당source checkout에서 PYTHONPATH=. .venv-sim/bin/python /tmp/analyze-reloc15-round.py <1|2|3>. 저장helper=tools/analyze_round.py. 전체raw/SHA256SUMS는GCP에보존.
