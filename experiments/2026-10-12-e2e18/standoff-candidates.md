# E2E18 파지 접근 지연: 근접 빔 소실 후진 후보 (v295–v296)

## 가설 확인 (r52 v273, r2, VM3 `raw/robots/r2/rgb`, 5장 개별 회수)
- 프레임 00496(225 s), 00529(238 s): 빔이 화면을 가득 채우고 위·아래가 잘림(너무 가까움). 00529는 상단·하단 모두 프레임 밖으로 이어짐.
- 00559(250 s), 00609(270 s), 00671(295 s): 빔 없음(바닥/벽만). 이미 몸을 돌리거나 이동한 뒤다.
- 결론: "가까워서 빔이 시야에서 사라진다"와 일치한다. 단, 잘린 빔이므로 사라지는 과정은 "끝점 없음(clipped) → 시야 밖"이다. `log.txt`의 `own_clip_recovery` 문자열은 0건(다른 원장 미확인). r2의 소실 직전 `BAND_CLIPPED` 길이는 확인 안 됨.
- 샘플 5장이라 일반화하지 않는다. 시드 61006 한 실행.

## 토글 (모두 기본 off)
| 토글 | 번들 | 내용 |
|---|---|---|
| `--beam-lost-standoff v1` | v295 | 마지막 본 빔(자기 지도 선분)과 현재 자기 오도메트리 거리 ≤0.35 m이고 앞쪽(±90°)이면 보정된 역방향 0.1 s 펄스로 자기 오도메트리 0.30 m(최대 12펄스, 10 s) 후진한 뒤 기존 turn→scan. 마지막 본 쪽으로 다시 돈다. 소실 1회당 1번. |
| `--arm-clearance-align-skip v1` | v296 | align 단계에서 자기 station 0.5 m 이내이거나 같은 자리(0.25 m)에서 2회 이상 후진했으면 clearance 연기를 건너뜀(센서 증거는 이벤트로 기록). |
| `--acquire-scan-fast v1` | v296 | 뷰 간격 2.0→1.2 s, turn 상한 3→2 s. |

- v295 = v273 + standoff. v296 = v295 + align-skip + scan-fast. 부모는 e2e18-v273만 허용하고 다른 조합은 거부한다.
- 입력 경계: 자기 RGB 기억, 자기 오도메트리, 자기 명령 이력만 쓴다. 정답 좌표·접촉·관절 측정은 쓰지 않는다.
- 한계: 후진 방향은 몸체 후방 고정이다. 뒤쪽 장애물은 기존 투영 충돌 검사(DEV는 기록만)에만 의존한다. 첫 소실 이후 반복 소실(v271 r2 5회 이상)은 기존 순환이 이어진다.

## 표준 방법 (참고 자료)
- 시각 서보에서 표적이 시야를 벗어나면 마지막 좋은 시점으로 돌아가거나 거리를 벌려 다시 잡는 것이 일반적이다. Chaumette & Hutchinson, "Visual servo control Part I/II", IEEE RAM 2006 — 기억 기반, URL 미확인.
- Nav2 도킹 서버(opennav_docking)의 staging pose 복귀 후 재검출·재시도: https://docs.nav2.org/configuration/packages/configuring-docking-server.html 은 404, 내용 미확인.
- 위 둘은 설계 방향의 근거일 뿐 이 구현이 그대로 따른 것은 아니다(우리 제약: 자기 RGB·오도메트리만).

## 시험
- tests/test_e2e_acquire_standoff.py 8/8, tests/test_e2e_camera_hold.py 46/46(v295·v296 등록 행 포함), tests/test_e2e_arm_clearance.py 12/12.
- tests/test_e2e_pregrasp_acquire.py 7/8: 1건은 sparse checkout에 없는 `experiments/.../evidence/*.jpg` 때문에 실패(내 변경과 무관, 미확인 아님·이 worktree의 파일 부재).
- 시뮬레이션 실행은 하지 않았다. 효과(SIM초 절감)는 확인 안 됨.
