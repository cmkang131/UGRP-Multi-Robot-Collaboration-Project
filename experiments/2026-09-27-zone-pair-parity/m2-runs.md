# M2 성공 실행별 재판정

S = 저장 RGB·발행 명령의 별도 PF 재구성. 원본 PF의 정확한 중단시각이 아니다. G = 상시 gate의 최초 거부, C = 현재 형상 여유의 최초 음수(복구 결과가 아님).
초기 C 뒤에도 원본 trace를 계속 읽어 G를 별도 측정했다. 정적 계획 거부는 열린 바닥/지원 범위 차이다. 시간은 원본 절대 SIM s.

| 실행 | 계획 | r1 S: G / C | r2 S: G / C |
|---|---|---|---|
| `zone-m2-pair-20260926/dev1-701-on` | 범위 밖 | 94.401 carry / 4.505 approach | 91.895 carry / 5.105 approach |
| `zone-m2-pair-20260926/dev1-702-off` | 범위 밖 | 80.566 wait_lift / 5.305 approach | 85.078 carry / 5.705 approach |
| `zone-m2-pair-20260926/dev1-703-off` | 범위 밖 | 77.559 wait_carry / 3.704 approach | 80.867 carry / 5.305 approach |
| `zone-m2-pair-20260926/dev1-703-on` | 범위 밖 | 77.559 wait_carry / 3.704 approach | 80.867 carry / 5.305 approach |
| `zone-m2-pair-20260926/dev11-811-dv2-off` | 통과 | 146.431 carry / 4.305 approach | 143.924 carry / 4.305 approach |
| `zone-m2-pair-20260926/dev11-813-dv2-off` | 통과 | 135.704 wait_carry / 5.505 approach | 139.012 carry / 2.100 approach |
| `zone-m2-pair-20260926/dev5-723-v2-off` | 범위 밖 | 138.310 carry / 2.902 approach | 132.997 wait_lift / 4.905 approach |
| `zone-m2-pair-20260926/dev5-801-v2-off` | 통과 | 134.300 carry / 3.905 approach | 134.200 carry / 4.505 approach |
| `zone-m2-pair-20260926/dev7-801-v2-off` | 통과 | 141.819 carry / 3.905 approach | 141.719 carry / 4.505 approach |
| `zone-m2-pair-20260926/dev7-802-v2-off` | 통과 | 144.927 carry / 4.105 approach | 146.531 carry / 4.305 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s711-off` | 범위 밖 | 82.471 carry / 미검출 | 79.865 lift / 3.303 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s711-on` | 범위 밖 | 82.471 carry / 미검출 | 79.865 lift / 3.303 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s712-off` | 범위 밖 | 98.411 carry / 4.905 approach | 95.905 wait_carry / 4.305 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s712-on` | 범위 밖 | 98.411 carry / 4.905 approach | 95.905 wait_carry / 4.305 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s713-off` | 범위 밖 | 95.504 carry / 2.100 approach | 87.784 wait_lift / 9.108 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s713-on` | 범위 밖 | 95.504 carry / 2.100 approach | 87.784 wait_lift / 9.108 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s714-off` | 범위 밖 | 87.183 carry / 3.103 approach | 84.175 wait_carry / 5.105 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s714-on` | 범위 밖 | 87.183 carry / 3.103 approach | 84.175 wait_carry / 5.105 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s715-off` | 범위 밖 | 85.378 carry / 3.504 approach | 82.371 wait_carry / 6.305 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s715-on` | 범위 밖 | 85.378 carry / 3.504 approach | 82.371 wait_carry / 6.305 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s716-off` | 범위 밖 | 94.501 wait_lift / 4.105 approach | 99.814 carry / 3.504 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s716-on` | 범위 밖 | 94.501 wait_lift / 4.105 approach | 99.814 carry / 3.504 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s717-off` | 범위 밖 | 79.163 carry / 5.505 approach | 81.569 carry / 3.704 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s717-on` | 범위 밖 | 79.163 carry / 5.505 approach | 81.569 carry / 3.704 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s718-off` | 범위 밖 | 81.268 wait_carry / 4.905 approach | 84.576 carry / 5.105 approach |
| `zone-m2-pair-20260926/stage1-3fdf011/s718-on` | 범위 밖 | 81.268 wait_carry / 4.905 approach | 84.576 carry / 5.105 approach |
| `zone-m2-pair-20260926/stage2-fa682a6/s812-off` | 통과 | 132.295 wait_lift / 4.905 approach | 138.411 carry / 5.105 approach |
| `zone-m2-pair-20260926/stage2-fa682a6/s812-on` | 통과 | 132.295 wait_lift / 4.905 approach | 138.411 carry / 5.105 approach |
| `zone-m2-pair-20260926/stage2b-ed15489/s821-off` | 통과 | 141.518 carry / 5.305 approach | 136.606 wait_lift / 3.704 approach |
| `zone-m2-pair-20260926/stage2b-ed15489/s821-on` | 통과 | 141.518 carry / 5.305 approach | 136.606 wait_lift / 3.704 approach |
| `zone-m2-pair-20260926/stage2b-ed15489/s822-off` | 통과 | 142.320 wait_carry / 7.305 approach | 145.629 carry / 195.052 carry |
| `zone-m2-pair-20260926/stage2b-ed15489/s822-on` | 통과 | 142.320 wait_carry / 7.305 approach | 145.629 carry / 195.052 carry |
| `zone-m2-pair-20260926/stage2b-ed15489/s823-off` | 통과 | 138.812 carry / 7.105 approach | 138.310 carry / 2.301 approach |
| `zone-m2-pair-20260926/stage2b-ed15489/s823-on` | 통과 | 138.812 carry / 7.105 approach | 138.310 carry / 2.301 approach |
| `zone-m2-pair-kiro-20260926/dev12-824-v3-on` | 통과 | 140.115 carry / 5.305 approach | 137.909 wait_carry / 8.707 approach |
| `zone-m2-pair-kiro-20260926/dev13-822-v3-off` | 통과 | 133.398 carry / 4.505 approach | 135.002 carry / 193.648 carry |
| `zone-m2-pair-kiro-20260926/dev14-824-v3-on` | 통과 | 143.423 wait_carry / 7.105 approach | 146.631 carry / 3.303 approach |
| `zone-m2-pair-kiro-20260926/stage2b-ed15489-completion/s826-off` | 통과 | 150.641 carry / 3.704 approach | 147.634 lift / 7.505 approach |
| `zone-m2-pair-kiro-20260926/stage2b-ed15489-completion/s826-on` | 통과 | 150.641 carry / 3.704 approach | 147.634 lift / 7.505 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s831-off` | 통과 | 136.105 wait_carry / 4.905 approach | 138.912 carry / 2.100 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s831-on` | 통과 | 136.105 wait_carry / 4.905 approach | 138.912 carry / 2.100 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s832-off` | 통과 | 147.233 carry / 5.505 approach | 148.035 carry / 3.504 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s832-on` | 통과 | 147.233 carry / 5.505 approach | 148.035 carry / 3.504 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s834-off` | 통과 | 139.413 carry / 4.305 approach | 142.220 carry / 4.905 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s834-on` | 통과 | 139.413 carry / 4.305 approach | 142.220 carry / 4.905 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s835-off` | 통과 | 145.929 wait_carry / 4.305 approach | 148.837 carry / 4.505 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s835-on` | 통과 | 145.929 wait_carry / 4.305 approach | 148.837 carry / 4.505 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s836-off` | 통과 | 146.030 lift / 7.305 approach | 148.937 carry / 2.902 approach |
| `zone-m2-pair-kiro-20260926/stage2c-ca44f66/s836-on` | 통과 | 146.030 lift / 7.305 approach | 148.937 carry / 2.902 approach |
