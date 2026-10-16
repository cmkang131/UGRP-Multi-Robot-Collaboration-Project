# mapbuild8 — 이동량 예측·자기 지도·지도 기반 위치 보정

ownership-ack. `mapbuild1` / `codex/mapbuild1` / PR #556, gcp5 단독. mapbuild7 R2는 인수 시 이미 `MAP_REGISTRATION_REQUIRED`(33.3 SIM초, 334장)로 종료했다. 기존 raw·요구표·실패를 유지하고 새 결과와 합산하지 않는다. 자기 RGB·발행 명령·고정 기구/K/D·허용 정적 지도만 추정에 쓴다. 시작 spawn/평가 좌표로 정적 좌표계를 만들지 않는다.

**최종 판정 NOT_READY. 새 물리 3/3회를 사용했지만 실제 운반 녹화0회다.** 세 실행 모두 초기 정적 등록에서 멈췄다. 지도 보정 구현·저장 프레임 비교는 완료했지만, LK/RBPF 기본 선택·적재 주행·ACT 학생·LLM E2E 성공 근거는 없다. 네 번째 물리 실행이나 관문 점수 재맞춤은 하지 않았다.

먼저 R2/R3의 `ambiguous_modes` 후보 점수와 모드 수, ±1σ 조건부 창을 gcp5에서 분석했다. 정적 지도에 등록되지 않은 실행에는 유효한 전역 위치 사전이 없다. 모드 자체를 창 중심으로 삼은 결과는 **조건부 진단**이며 실제 이동량 사전이나 올바른 초기 위치가 아니다. 최적 모드/spawn/평가 좌표를 창 중심으로 채택하지 않았다.

## 확정 요구표 — mapbuild6 바이트 유지

| 지점 | 기준 | 근거·원본 |
|---|---|---|
| 근거리 인계 | XY≤200.751mm, `abs(yaw)+atan2(XY,.84831457-XY)`≤21.4233° | 기존 교사79800–79839의 거리 P5/P50/P95=.647563/.848315/1.080183m, facing 오차 P95=21.4233°. [requirements.json](requirements.json)의40개 plan/result 경로·SHA. native87420–87459는 미회수라 승인된 기존 원장 사용. 학생 수용의 공동 분포 보장은 아님 |
| 자리 도착 | 자리 중심60mm, 가까운 자리 식별200mm, 화물 중심의 구역 내 여유280mm | 정적 지도 `zone_slots`·구역/화물 크기. 정적 원본 `/home/ugrp/ugrp-sim/src/mapbuild6-60db80c1a/maps/zones/zone_wide_door_geometry_v3.json`, SHA `be9a571b…` |
| 문 | 폭500mm. 측방오차+`.12*abs(sin yaw)+.105*abs(cos yaw)`≤250mm | 같은 지도 door_1 및 `harness/zone_team_footprint.py` 고정 충돌 외곽. 실제 팔·적재 외곽은 추가 자격 필요, 미측정은 통과 아님 |

요구표 SHA256 `d9f3c1f3a00273be3aa901613d01386fa493b1ed5edb561e40a58d367360875c`. 과거 CPU 교사 원장은 요구 분포의 출처이며 이번 native 성공률로 합산하지 않는다.

## 방향을 가른 모드 표

| 저장 자료 | 경쟁 후보 수 | 2위 점수차 | 각 후보 중심 ±1σ 안 단일 | 실제 정적 사전 |
|---|---:|---:|---:|---|
| mapbuild6 R2 | 5 | .051159 | 5/5 | 없음 |
| mapbuild6 R3 | 5 | .042102 | 5/5 | 없음 |
| 인수 mapbuild7 R2 집기 뒤 | 6 | .009778 | 6/6 | 없음 |
| 인수 mapbuild7 R2 최초 pan | 210 | ≈0 | 210/210 | 없음 |
| 새 R3 실제 전역 입력 재구성 | 2 | .426655 | 2/2 | 없음 |

정의는 기존 `.50` 센서 점수 대역에서 `.15m` SE(2) 거리로 분리한 후보다. 독립 posterior 모드 개수를 증명한 것은 아니다. 원본·σ·모든 후보는 [방향표](results/mode-direction-table.json), [최초 pan](results/inherited-prescan-mode-table.json), [새 R3](results/r3-mode-direction.json). 새 R3는 실제 사용 선분/카메라 원점/차체 공분산을 재구성해 점수·잔차·점수차·랭크까지 원래 실행과 정확히 일치했다. 두 후보는 약π 방향으로 갈라진다. **등록 뒤 국소 사전 창은 유효한 구조지만, 미등록 상태를 해결해 주지는 않는다.**

## 구현 범위

`selfmap_map_correction_v1`(기본 off/이번 후보 on)은 매10Hz에 자기 명령+LK 이동량과3×3 공분산을 전파하고, 기존1 SIM초 주기에 현재 벽 scan을 과거 자기 서브맵/등록된 정적 지도에 같은 ±1σ 사전으로 맞춘다. 기존 CSM 거리장·센서 모델·관측 가능 방향 투영·중첩/잔차/모드 기준을 재사용했다. 현재 scan은 정합 뒤에만 삽입하고 과거 키프레임은 불변이다. 두 정합을 독립 관측인 것처럼 이중 융합하지 않는다. 전역 탐색은 미등록 또는 lost 재위치 추정이다. 장기 pose graph/loop closure 최적화는 미구현이다.

작은 σ 창에서0변위도 경계로 거부하던 격자 오류를 회귀검사로 고쳤다. 거부 시 위치/분산은 유지하고 유효 관측만 motion prior와 함께 넣는다. R1의 참조 지도 고갈을 고쳤지만 이 정책의 정확도 관문 통과를 뜻하지 않는다. 기존 점수·관문 σ배율·물리/접촉 상수는 재맞춤하지 않았다.

R2 자체 RGB에서 같은 빈 FOLDED 양의 회전 명령232개 구간의 평균/전체 예측 공분산을 동결한 `own_command_motion_v1`도 기본 off다. 동일 PWM·바퀴값·펄스 길이·100ms 간격에서만 사용한다. 다른 방향/적재/펄스에 보간하지 않는다. [동결 자료](calibration/own-command-calibration-r2.json), [API 계약·해시](API.md).

`servo_fk_carry_v1`은 자기 발행 서보로 닫힌 집게에서도 고정 체인의 카메라 자세를 계산한다. 집게 슬라이더는 카메라 조상이 아니며, 가림 마스크는 발행 grip PWM을 유지한다. 기구/K/D/FOV 변경0. 인수 R2 닫힘131프레임의 독립 평가 P95=.970mm/.280°([결과](results/carry-fk-summary.json)). 새 적재 운반 자격은 아직0이다. 명목 카메라 높이66.7–138.0mm가 기존 CSM 하한150mm를 하회하는 범위의 스캔 분산 자격은 남아 있다.

## 새 실행별 결과 — 서로 다른 후보, 성공률 합산 안 함

| 실행·고정 소스 | 프레임/SIM초 | 차체 이동 | 끝 사유 | 보정 시도/채택 |
|---|---:|---:|---|---:|
| R1 `cfaf3b52c` | 277/27.6 | .178m | `ambiguous_modes`, 차체 회전이 명목159틱에서 약198°로 끝남. 일부 구간 벽 미관측 | 10/0 |
| R2 `fcc80b7a5` | 378/37.7 | .255m | `high_residual` .169803m>.15m. 고정 FOLDED+실제 한 바퀴 자기 추정 | 35/5(변위 전부0) |
| R3 `2f7cfacca` | 389/38.8 | .215m | `ambiguous_modes` 점수차.426655<.50, 잔차.086078m/중첩.9562 | 35/12(비영 보정4) |

모두 `MAP_REGISTRATION_REQUIRED`, HOST_ERROR0, cap_end0, CPU/GPU noslip0. actual transport/닫힘 명령/문/구역/복귀/내려놓기/내려놓은 뒤 둘러보기는 새3회 모두0이다. R3의 자기 추정6.2977rad/265틱은 R1 자기 응답 P05에서 도출한692틱 계산 상한 이내다. wall 시간은 판정에 사용하지 않았다.

## 같은 프레임 OFF/ON — 봉인 뒤 평가만 GT 사용

기준은 **차체 중심 SE(2), 시작 자세 정렬 한 번, 척도1**이다. `off`는 같은 LK+명령 융합 증분에서 지도 보정만 끈 것이고, `lk`는 별도 순수 LK 열이다. 평가 파일을 정합·동결·보정 채택에 넣지 않았다.

| 실행/방법 | 끝 XY mm | 끝 yaw ° | XY RMSE mm | 최대 XY mm | 끝 XY/차체 이동 % |
|---|---:|---:|---:|---:|---:|
| R1 OFF=ON | 25.1 | 2.60 | 22.9 | 34.9 | 14.1 |
| R2 OFF=ON | 27.9 | 24.98 | 28.6 | 56.8 | 10.9 |
| R3 LK | 50.2 | 3.00 | 35.3 | 55.2 | 23.4 |
| R3 OFF | 43.2 | 3.31 | 29.8 | 48.0 | 20.1 |
| R3 ON | **149.8** | **5.60** | **80.6** | **152.0** | **69.8** |
| R3 RBPF | 46.3 | 3.36 | 40.4 | 67.3 | 21.6 |
| R3 명목 명령 OFF 소거 비교 | 71.4 | 28.05 | 51.5 | 75.3 | 33.3 |

거의 제자리 회전이므로 짧은 차체 중심 이동을 분모로 한 %를 수m 운반의 drift로 외삽하지 않는다. 위 모든 끝점은 **준비 회전의 끝**이다. R3 ON 끝점은 인계 수치 예산(200.8mm/21.42°) 안이지만60mm 자리 예산 밖이다. 실제 인계/도착 관문 통과나 실패로 바꿔 보고하지 않는다. 원본 수치는 [R1](results/r1-executed-evaluation.json), [R2](results/r2-executed-evaluation-final.json), [R3·명령 소거 비교](results/r3-executed-evaluation.json).

## 거부·오차 원인 분포와 확인 범위

| 범주 | 관측 근거 | 결론/남은 확인 |
|---|---|---|
| 새 실행 진행 차단 | 초기 등록3/3 거부: 모호2, 큰 잔차1 | 시작 미상 전역 초기화가 미해결. 최적 후보 강제 채택 금지 |
| R2 회전 명령 | LK 실패21구간 yaw 잔차합+17.495°, LK 측정232구간 융합+7.553°(순수 시각 −.078°) | 큰 명목 명령 편향 확인. R2 RGB만으로 고정한 명령 모델의 R3 같은 프레임 소거 비교는28.05°→3.31°; 빈 동일 회전만 자격 |
| R3 자기 서브맵 오채택 | 12채택 중8개0변위,25.6/26.6/27.6/28.6초4개는 모두 XY/yaw 악화. XY34.9→47.1,50.5→60.9,60.6→82.7,81.0→149.3mm | 새 ON의 주된 관측 악화. 잘못된 자기 지도 배치/상관된 참조에 끌림을 추가 분리해야 함. 아직 독립 원인 완전 규명 아님 |
| 벽 경계/투영 | 해당6장 overlay에서 실제 벽발 검출. GT 차체로 놓은 같은 scan의 P95 최근접 정적 벽 거리는13.5/18.2/16.8/20.2mm | 색 오검출만으로 악화를 설명하는 근거 없음. 이4점의 삽입 후 P95는56.0/89.5/126.5/155.9mm로 증가. GT는 진단 전용, 정답 벽 대응의 증명 아님 |
| R3 잔여 LK 이동량 | 회전 측정239구간 XY 증분 잔차합.431m, 명령 대체25구간.0229m | 잔차합은 최종 SE(2) 기여량이 아님. yaw/XY 상관·서브맵 왜곡을 다음에 분리 |
| 사전 σ | 지원된35시도 중 실제 자세를 포함하는 사전 창18/35, 각 축25/26/18 | ±1σ를 확률 보장으로 해석 불가. GT로 σ배율 재맞춤0 |

오채택은 별도 평가에서 전후 오차가 증가한 사건이며, 전체 독립 시도 성공률이 아니다. static 등록 채택0/0이므로 잘못된 전역 채택률은 미측정이다. [R2 원인표](results/r2-vo-cause-table.json), [R3 원인표](results/r3-vo-cause-table.json), [오채택 원장](remote-records/correction-harm-r3.json), [투영/배치 분리](remote-records/scan-error-r3.json). 원인 확인 전 임의 상수 수정 없이 다음 묶음은 [제안만](next-proposal.md) 남긴다.

## 관문·재현·검증

프레임 funnel은 R1 `277→134→10→0`, R2 `378→330→35→5`, R3 `389→341→35→12`(전체→벽 보임→지원/주기 통과→보정 채택)다. 실제 운반 관문은 각 실행 `1→초기 등록0→운반0`이다. [rejection_table.json](rejection_table.json)에 누적 수·거부 사유·물체·미측정 틈·원본·재현 명령을 연결했다. [next-queue.json](next-queue.json)은 ready=false다.

R1/R2의 프레임 funnel은 저장 결정 원장에서 사후 재구성했고 R3부터 실행기가 직접 썼다. 이전 표를 연결한 각 실행 큐는 별도로 보존한다. R1/R2 전체 원래 argv는 미회수여서, 재현 명령은 고정 소스·큐·명시 옵션에서 재구성했음을 표시했다. R3 argv는 runtime 원본이다.

- 고정 실험 소스/실행 명령/평가 순서: [reproduce.json](reproduce.json), 원본 `/home/ugrp/ugrp-sim/runs/mapbuild8/`.
- 원본574/777/800=2,151파일, 봉인 예측2/3/3=8파일 재해시 불일치0. [무결성 영수증](operations/final-integrity.json), 실행별 [raw SHA 목록](remote-records/recording-r3/SHA256SUMS.json). 원본 이미지/상태/전역 비용 배열은 VM 디스크에 보존, Mac에는 요약/해시/몽타주/작은 검토 영상만.
- gcp5 비물리 회귀103개 통과. 최초100통과/3실패는 C++ 컴파일러 부재; 설치 후 관련21개 모두 통과. 전체 프로젝트 CI 통과 주장은 아님. [검증 기록](validation.json).
- 새3회 실패 직전10 SIM초10Hz 링 보존. R3 전체0–38.5초2Hz 개요+r1+r2, 말미28.8–38.8초10Hz r1과 실패 주변6장 직접 확인. gcp5에서3배속 합성·ffprobe, Mac 앱 실행0. [검토 타임라인](playback-review.md), [회수 해시](operations/playback-retrieval.json). 독립 성공 운반 영상은 없어 성공1개 비교 조건은 미충족이다.
- stackaudit `45623168`의 새 `selfmap_map_correction=on` 조건만 부분 확인했다. R3 선언13 current/15 unknown, 전체 admission은 blocked다. 진단 실행을 full-stack/heading-first 인수로 승계하지 않는다. 현재 녹화기의 동결6f 경로 커널 한계와 적재 스캔 자격을 [API.md](API.md)에 명시했다.
- 종료 전 타 리스0·작업 Python/MuJoCo/ffmpeg0·GPU0%/0MiB를 확인하고 자기 리스만 해제했다. **2026-10-17 03:51:11.794 KST gcp5 TERMINATED**. [부하 확인](operations/close-load-check.json), [실제 상태](operations/instance-stopped.json). idle20·budget-stop 유지, 다른 VM 시작0. 공유 ops의 gcp3 418뷰 분석 요청은 이번 gcp5 단독 범위로 미수행이며 소비자에게 알렸다.

## 채점 전 결정 규칙

같은 실제 운반 녹화·같은 프레임에서 보정 OFF/ON을 비교한다. 차체 중심 SE(2), 시작 자세 정렬만, 척도1이다. 요구표는 mapbuild6의 바이트를 유지한다(인계 XY≤200.751mm, 방향결합≤21.423°, 자리60mm; 문은 방향과 차체/적재 폭을 별도 평가). 실제 문·구역·복귀·내려놓기·둘러보기·적재 구간이 빠지면 전체 NOT_READY다. 일부 접근 구간 통과를 운반 성공으로 보고하지 않는다.

둘 다 요구를 만족하면 단순한 LK를 기본으로 두고 RBPF off, LK만 실패/RBPF 통과면 RBPF, 둘 다 실패면 원인 분포에 따른 다음 수정안을 제안한다. 사용자 최신 결정에 따라 LK 선택과 별개로 **자기 지도 및 정적 지도에 대한 위치 보정은 필요**하다. 이번 새 후보 `selfmap_map_correction_v1`은 기본 off/후보 on으로 검증하고 기존 결과를 소급 변경하지 않는다. GT는 봉인 뒤 별도 오차 평가에서만 읽는다. 잘못된 보정 채택은 평가 전용으로 전후 오차가 악화됐는지를 수치로 보고한다.

## 먼저 확인한 표준 구조·참고 자료

- [Thrun/Burgard/Fox, Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/): 출판사 서지 확인. 책 전체를 새로 열람했다고 주장하지 않는다.
- [Fox et al. 1999, Monte Carlo Localization](https://robots.stanford.edu/papers/fox.aaai99.pdf), §Markov Localization/MCL: 이동 예측과 관측 갱신, 시작 미상일 때 전역 다봉 분포. [Nav2 AMCL 공식 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/README.md): 알려진 지도 위치 추정과 global localization을 구분한다. lidar 정확도를 색 경계에 승계하지 않는다.
- [Hess et al. 2016, Cartographer](https://research.google/pubs/real-time-loop-closure-in-2d-lidar-slam/), [공식 알고리즘 설명](https://google-cartographer-ros.readthedocs.io/en/latest/algo_walkthrough.html) Local/Global SLAM: 이동량 사전에서 현재 scan→submap 정합, 국소 submap 삽입, 별도의 강한 loop-closure 검증. 완전 Cartographer 포팅이나 pose graph 구현을 주장하지 않는다.
- [Olson 2009, Real-Time Correlative Scan Matching](https://april.eecs.umich.edu/media/pdfs/olson2009icra.pdf), §III-A/B: 관측우도×이동사전, prior가 정한 가능한 SE(2) 창의 상관 탐색. 기존 `CorrelativeMatcher`/거리장/센서분산/관측가능성 코드를 재사용한다.
- [Montemerlo et al. 2002, FastSLAM](https://robots.stanford.edu/papers/montemerlo.fastslam-tr.pdf), Factored Representation: 경로 posterior와 경로 조건부 지도 분해. 기존 RBPF 비교를 유지하며 새 필터를 발명하지 않는다.
- [Campos et al. 2021, ORB-SLAM3](https://arxiv.org/pdf/2007.11898), §III/IV-A/V: local tracking·lost·relocalization·새 지도와 map merging 구분. feature DB/MLPnP 성능을 이번 벽 scan에 승계하지 않는다.

## 보존·운영

분석/물리/렌더는 gcp5. Mac은 코드·요약·몽타주만. `warp_native_contact_v1`, noslip0, idle20/budget-stop 유지, wall 실행 상한 없음. CPU VM 시작/키·에이전트 자격증명 전송/GUI/모델 호출0. 실행 코드는 커밋 후 고정한다. 관문 funnel·모든 실패·raw 위치·SHA·재현 명령을 남긴다. 임대 및 실제 프로세스/GPU를 점검한 뒤 자신만 남았을 때 gcp5를 정지한다.
