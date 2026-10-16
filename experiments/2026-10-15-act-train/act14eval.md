# ACT14 — ACT13 고정 모델의 검증 손실·첫 폐루프 평가

**실행·회수 완료, Haiku 독립 재집계 대기.** DEV이며 연구/기본 제어기 승격은 승인하지 않았다.
새 시드20개×모델2개 본40회와 별도 탐색6회를 모두 기록했다. 실행 오류/HOST_ERROR0,
미회수0이다. 아래 성공 수는 기존 평가 기준에 따른 **자동 채점**이며 학생 성공의 독립 확증이 아니다.

| 모델 | 안정적 들기(자동) | 완료 신호까지 충족 | cap_end | 학생 done 발생 | 본 실행 |
|---|---:|---:|---:|---:|---:|
| p0 / history dropout0 | 1/20 | 1/20 | 6/20 | 14/20 | 20/20 |
| p02 / dropout0.2 | 1/20 | 0/20 | 7/20 | 13/20 | 20/20 |

p0 `91434`는 평가상 들기와 학생 완료 신호를 모두 냈다. p02 `91426`은 평가상 들기 뒤에도
완료 신호가 없어90 SIM초 cap_end였다. 완료는 stable lift·낙하 없음·학생 done·비cap을 모두 요구한다.
조기 done 자체는 성공으로 세지 않는다. 탐색6회는 안정적 들기2/6, 완료0/6, cap_end4/6이며
본40회와 합산하지 않는다. 두 모델의 우열/일반화나 실물 성공을 이 표로 확정하지 않는다.

| 모델 | 기존 마지막 학습 총손실 | 동일 추정량 train45 | val5 | val/train |
|---|---:|---:|---:|---:|
| p0 | 0.132395 | 0.191404 | 0.200776 | 1.04896 |
| p02 | 0.132137 | 0.181773 | 0.208217 | 1.14548 |

검증은86865–86869 전체5에피소드/1811행, 학습 비교는45개/16275행이다.
manifest SHA-256 `9ed3f155c87c8b53631ae89480bb0a6d868cc2a4c12341ff1e0579541deff925`. 고정 step10000을 사용했고 val로 모델/임계값을
고르거나 재학습하지 않았다. train/val 모두 eval·zero latent, 유효 행동만의 이동 L1/14 +
TRAIN 사전확률 가중 완료 BCE다. 기존 로그의 학습 손실은 VAE KL·dropout을 포함해 직접 같은 척도로
비교할 수 없다. 같은 추정량에서 val이4.9%/14.5% 높다. val5개만으로 과적합이나 폐루프 실패 원인을
확정할 수 없다. 낮은 오프라인 손실이 폐루프 성공을 보장하지 않았다.

| 모델 | 후보/입력 감사 | 접근 | 기능 정렬 | 양측 접촉 집기 | 안정적 들기 | 완료 |
|---|---:|---:|---:|---:|---:|---:|
| p0 | 20/20 | 12 | 2 | 2 | 1 | 1 |
| p02 | 20/20 | 12 | 1 | 1 | 1 | 0 |

관문별 received/passed/rejected, 프레임·고유 실행 이벤트 누적 수, 접촉 geom 이름/최소 gap,
원본/해시/재현 명령은 [funnel](act14-funnel.json)에 있다. 최초 미통과는 접근16회, 정렬21회,
들기 확인1회이며, 그 밖에 안정적 들기 뒤 학생 완료 신호가 없는 cap_end1회다.
이는 **판정된 최초 관문**이지 확정된 물리/학습 원인이 아니다. 접촉 물체 이름도 관측값이며
원인으로 단정하지 않는다. 모든 실패 실행의 자기 프레임6장 이상을 보존했다.

장면·카메라·물리 의존성은 교사 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`,
act11 rotation-on 기준/act12와 같은 GCP `ugrp-sim-gcp1` / n4-highcpu-64다.
초기 장면 XML·첫 자기 JPEG·카메라 pos/quat/intrinsic/resolution·초기 발행 PWM을
독립 구성과 대조해 모두 바이트/값 일치를 확인했다([증거](act14-scene-parity.json)).
시작 SIM시각도1.3초로 같았다. 46회 camera-runtime 해시는1종으로 같았다.
초기 PWM은 `servo_command_pulses`의 발행 이력이며 측정 qpos가 아니다.

`--teacher-start-v1`은 기본 OFF다. 켠 평가만 교사와 같은 .6–1.1m 시작 분포와
scene.setup 직후 발행 이력을 쓰며, 기존 학생 경로의 추가 folded 명령/1초 대기를 제거한다.
ACT 학생은 근거리 접근·정렬·집기를 직접 수행했다. 격리 CPU worker 입력은 자기 RGB4장·
자기 발행 명령16개·고정 스킬/종류/자리 번호표뿐이다. 좌표·접촉·관절·teacher/IK 교정은 없다.
정답은 별도 평가 원장에만 기록했고 `SoloSequence.update(now, student_done)`에는 넣지 않았다.
모든 실행 `invisible_measurements=held_world_reads=top=0`, 금지/교사 입력 필드0,
비finite 추론/형식 오류0, weld OFF다. 초음파·공용 top 입력·판단 LLM 호출은0이다.

본 seed91420–91439는 색별5개, 별도 탐색91440–91442다. act11 8317100–8317139 및
act12 86820–86869와 겹치지 않는다. 로컬235파일·원격3716결과/계획 파일과 원격 예약을 확인했다
([시드 검사](act14-seed-inventory.json)). 이미 쓴 어려운 act11 시드를 재사용할 수 없으므로
새 시작 방위오차가 큰 시드를 앞에 뒀다. 23개 spawns·scenario·item·시도수·handoff오차가 고정 교사 샘플러와 일치했다.
스킬은 grasp, chunk/n_action_steps8,10Hz, ensemble OFF, actor CPU1thread, 외부 회복 외란 OFF다.
ACT에는 경로 탐색이 없고 static setup 검사는 기존400/2000회 계산 상한이다. 종료는90 SIM초,
기존1800 wall초는 호스트 오류 watchdog만으로 행동 선택에는 쓰이지 않는다.

탐색/손실 소스 `3bd9e013ed99ea0b05982bb90e2a6852529eb2a8`,
본 시험·최종 재집계 소스 `8a43837598504e774532df463ff67836785958d6`. 기록 전용 수정으로 학생 명령 경로는 바꾸지 않았다.
정적 거부표는 실제로 거부한 predicate의 물체 ID와 그 기준 대비 signed gap을 기록하도록 고쳤다
(start_blocked19, 후보42→23 유지). 온라인 들기 funnel의1표본 지연도 제거했다.
탐색 최초 funnel은 교사 명목 자세를 학생 필수 조건처럼 취급해 평가상 들기와 불일치했다.
최종 funnel은 명목 정렬(.008m/.04rad) **또는 기존 양측0.5N 접촉**을 기능 정렬 근거로 쓴다.
접촉/들기는 선행 관문의 기능적 통과를 증명한다. 새 수용 오차나 정책 보정을 넣지 않았다.
접근 .08m 및 들기12mm/10°/양측0.5N/3 SIM초는 고정 교사/기존 LiftScore 기준을 그대로 썼다.
완료 score0.65도 기존 decoder 고정값이며 이번 val/시험에서 조정하지 않았다.
최초 탐색 표·원본은 보존했고 [수정 재집계](act14-pilot-funnel.json)를 본 큐에 연결했다.

실제 요청 큐는 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-act14-main-8a438375.json`이며 `rejection_table`은
`/Users/changmin/projects/ugrp/outputs/act14eval-a70c1588/pilot-funnel-corrected.json`로 파일/해시가 일치한다. 남은24회 큐도 같은 표를 연결했다.
자기 작업 최대 동시16(요청 상한16), 전역 예약 포함 최대
29/40이었다. 첫 동시 묶음의30 SIM초 완주9개
wall/SIM 중앙3.06055·최대3.30193, 조기 done5개는 별도다. 단독 첫2개와 합친 값으로 동시 성능을
부풀리지 않았다. 본 전체 wall/SIM 중앙은 p0 3.184, p02 3.090.

46회 각각 처음·중간·끝6프레임씩276개 슬롯을 직접 봤고 첫30 SIM초도4회×6장 별도로 봤다
(일부 중복). 시각은 [검토 원장](act14-frame-review.json)에 있다. 최대 간격18 SIM초로60초 규칙을
충족한다. 대상이 화면 끝에 치우치거나 사라지는 모습, 근거리 접촉 전에 done으로 끝나는 사례를
확인했지만 손이 화면 밖인 구간의 RGB만으로 들기 성공을 확정하지 않았다.
Mac에는 요약·몽타주·실패 선택 프레임만 남기고 원본 전체는 GCP 영속 디스크에 보존한다.

모든 실행·실패·원본 위치·원본 summary SHA와 전체 파일 해시를 가진 분석 원장의 SHA는
[요약 JSON](act14eval-summary.json)에 있다. raw는 `gcp1:/home/ugrp/ugrp-sim/runs/act14-*`다.
종료 뒤 전체 SHA256SUMS를 검증했고 큰 JSON/JSONL은 zstd 무손실 압축·복원 SHA 대조 및
COMPRESSED.jsonl 기록 뒤 보관한다. 원래 해시 목록을 유지하며 이후 파일은
SHA256SUMS-post-compression으로 다시 검증한다. 독립 full raw 백업은 아직 없다.
Mac 회수/운영 기록은 `/Users/changmin/projects/ugrp/outputs/act14eval-a70c1588`다.

기존 L4 `ugrp-act-l4-pilot1`에서 손실을 계산한 뒤 **TERMINATED**를 확인했다.
8h STOP·idle20분·budget-stop ACTIVE를 유지했다. 크레딧 잔액과 실청구는 독립 확인하지 못했고
예산 메시지는 집계 지연이 있다. gcp1의 다른 작업은 중단하지 않았다.
두 모델의 actor8파일을 L4→gcp1에서 원본 크기/해시와 대조했으며, 비교 모델도
[새 GitHub Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261015-act13-961aa751)에
보존했다. 각 ZIP9파일의 실제 재다운로드·전체 SHA·CPU worker ready를 확인했다
([배포 검증](act14-model-release-verification.json), `configs/model_artifacts.json`).
학습 데이터/optimizer 전체 백업이나 학생 성공 확증과는 별개다.

관련 로컬 시험은 `tests/test_grasp_act_act14.py tests/test_grasp_act_pilot.py`:13 passed/1 skipped
(Mac torch 미설치). 빠진 padding/BCE 수치 검사는 기존 gcp1 ACT 환경에서 별도로 통과했다.
고정 LeRobot 설치본(commit89236ea0, 파일 SHA8d622935319af7d03f1efd95d51e726af2921010f7e4f5ec3742f62280493111)
에서 eval/zero-latent 동작을 확인했다. 설치본/실행 argv는 로컬 운영 기록에 있다.

재집계 예시(원본을 덮어쓰지 않고 새 출력 경로 사용):

```sh
cd /home/ugrp/ugrp-sim/src/8a43837598504e774532df463ff67836785958d6
.venv-sim/bin/python -m scripts.analyze_grasp_act_act14 --root /home/ugrp/ugrp-sim/runs/act14-main-p0-91434-8a438375 --output /home/ugrp/ugrp-sim/act14-recount-NEW
```

남은 일은 조정자의 Haiku 독립 재집계와 다음 학습/실행의 판단이다. 이번 결과로 학생을
채택하지 않는다. 근거리 손코드 대체·교사 보정·후속 재학습은 수행하지 않았다.

최종 보관 검증: [46회 압축 후 해시·소유 프로세스·VM·대표 보존](act14-verification.json).
자기 프로세스/임대/예약은0/0/0이다. p0/p02 대표 원본과 자기640×480/10Hz 영상은
GCP `representative-act14-{p0,p02}-8a438375`에 milestone로 따로 복사해 파일 해시/영상 프레임 수까지 확인했다.
대표 영상은 Mac으로 회수하지 않았다. 모델 목록 회귀시험10 passed도 추가 통과했다.
