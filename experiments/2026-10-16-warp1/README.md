# warp1 — ACT solo 교사 MJWarp 배치 경로

**NOT_READY — DEV, 배치 물리·명령·RGB 파일럿 종료 / 전체 ACT 이식 미완료.** 기본 off `physics_backend=mjwarp_batch_v1`. PR #524 `142dbf04` 위에 쌓으며 기존 C 실행기 파일은 변경하지 않는다. 최종 수치는 [summary](summary.json)·[누적 관문/거부](rejection_table.json)·[측정표](measured-results.md)에 기록했다. 장면 선택과 ≥95%·최소40회 자체 교사 관문은 HOLD_SCENE·미승인이다.

[이식 설계와 직접 MjData 읽기 목록](design.md) · [공식 자료와 확인 범위](references.md) · [초기 거부 분포](rejection-before-runtime.json).

물리/명령/RGB transport는 배치화한다. 교사 상태기계·IK·C ray 가시성 adapter에는 세계별 Python 루프가 남는다. 성공 평가는 GPU contact force와 별도 Score이며 teacher로 반환하지 않는다. 자기 RGB·발행 이력·visible+not-held 대상 상대량 경계를 유지하고 close~open 구간 lazy read를 차단한다. 학습 기록·ACT 학생 통합은 별도 미완료이며 미승인 기록은 거부한다.

장면은 현재 `grasp_act_scene_v1 / floor_light_v1 / v3 runtime camera / real_v1 stiffness / native v7 / mesh rollers / weld off`이다. scenetex5는 아직 적용하지 않는다. 반투명 구역의 C/Warp RGB 차이는 보존·보고하고 장면을 숨기거나 바꾸지 않는다.

## 실행 경계

Mac에서는 비물리 시험만 한다. 실제 실행은 `ugrp-sim-b-1014` / `ugrp-act-l4-gcp2` 및 CPU 비교 `ugrp-sim-gcp2`만 쓰며 임대 파일을 먼저 만든다. L4 4시간 상한, 기존8h STOP·idle20분·budget-stop 유지. 다른 작업 임대/프로세스가 있으면 VM을 정지하지 않는다. raw 분석/영상 생성은 gcp2, Mac은 요약·몽타주·검토 영상만 회수한다.

표준 catalog ID `warp-act-teacher`는 `scripts.run_warp_act_teacher` 어댑터를 가리킨다. 직접 CLI의 `--physics-backend` 기본은 off이며 macOS·다른 프로젝트/VM을 simulator import 전에 거부한다. 실제 명령·소스 SHA는 각 실행 summary의 reproduce에 보존한다.

```sh
python -m scripts.run_warp_act_teacher --physics-backend mjwarp_batch_v1 \
  --teacher-source /home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e \
  --plan /home/ugrp/ugrp-sim/pilot-plans.json --episode 0 --nworld 16 \
  --compiled-reference-v1 /home/ugrp/ugrp-sim/runs/warp1/export-osmesa-seed0/compiled-312.json \
  --compiled-geometry-312-v1 /home/ugrp/ugrp-sim/runs/warp1/export-osmesa-seed0/compiled-geometry312.npz \
  --cap-s 60 --vm-hourly-usd 1.096 --out /home/ugrp/ugrp-sim/runs/warp1/NEW_UNIQUE_RUN
```

`--world-episodes`는 세계별 plan index를 받는다. 같은 정적 XML에서 free-joint 초기 pos/quat 선언만 다른 세계를 묶고 정적 지도·재질·카메라·기하가 다르면 거부한다. 같은 seed를 복제한 처리량 world를 독립 성공률 표본으로 세지 않는다. 물리 integration/relay의 선택 world 초기 리셋 진단은 구현했지만, 진행 중인 교사·관측 이력 리셋과 새 모델 교체는 미구현이다.


## 완료한 검증과 한계

- 비물리 **42 passed**. 실제 CameraRobotPort와400tick fractional PWM·명령 기한을 비교했다. camera port blob은 frozen6f와 같음(`63a44a8f`). Mac 물리·렌더·학습·GUI0.
- C3.12/n4-highcpu-64: 같은 source plan8317100/8317104/8317101 **3/3** 파지·들기·놓기 완료(40.8/44.1/43.8SIM초). 각 실행 `invisible_measurements=0`, `held_world_reads=0`. C 검증을 MJWarp 성공률로 승계하지 않는다.
- MJWarp N16 진단: 같은 seed/물리 모델, 서로 다른 기존 r1 시작 위치3종의 qpos·첫 RGB를 보존했다. 선택 world0 리셋 뒤10개 persistent field에서 선택값 복원/비선택값 보존을 확인했다. 실제 교사·이력의 중간 reset이나 성공률 표본이 아니다.
- 기본(no-sleep) MJWarp N1 시드8317100은1/1 파지·들기·놓기 완료(40.7SIM초), 두 입력 금지 카운터0이다. 별도 native-sleep 후보는 N1 시드8317100 성공1회(40.6SIM초), 추가 시드8317104는17SIM초 자원 cap_end1회다. N16은 동일 시드8317100 복제16/16 성공(40.6SIM초)이며 독립 시드는1개다. C/Warp5mm 동등성을 요구하거나 성공으로 대신 세지 않는다.
- 새 source의 실제 gcp2 funnel smoke는 cap0.1SIM초에 frame→not-held→visible→measurement **1→1→1→1**, 입력 수를 확인했다. 중단 probe에서 찾은 짧은 로그의 압축 경로 문제를 고쳤다. 새 gcp2 중단 probe는2프레임의2→2→2→2, cap_end1·completed0, 실제 raw 경로와 거부 원장까지 확인했다. 실패/중단에도 같은 파일을 flush한다.

## RGB 포함 처리량 (짧은 prefix, 공유 L4)

모든 세계에640×480/10Hz RGB·K/D/fisheye remap·JPEG·고정 교사를 포함했다. 같은 seed 복제이며 독립 시드 수는1이다. `SIM초/초`는 초기화를 뺀 loop aggregate, `SIM초/$`는 초기화 포함 VM 전체 단가 가정이다. CPU는 n4-highcpu-64의16개 독립 C 프로세스다.0.1SIM초는 한 tick이라 정상 상태 처리량·접촉 후 성공 에피소드 비용의 근거가 약하다. 실험 간 공유 부하도 달라 가속 채택 판정을 하지 않는다.

|경로|세계당 SIM초|aggregate SIM초|loop SIM초/초|초기화 포함 SIM초/$|
|---|---:|---:|---:|---:|
|C CPU16|0.1|1.6|아래 cold0.3053만 측정|349.44|
|MJWarp N16|0.1|1.6|0.07223|131.80|
|MJWarp N64|0.1|6.4|0.19476|369.81|
|MJWarp N256|0.1|25.6|0.40215|736.55|
|C CPU16|4.0|64|아래 cold3.4360만 측정|3933.11|
|MJWarp N16|4.0|64|0.04412|133.50|

가정 단가 L4$1.096/h, n4$3.145/h. 기존 실행 추정 단가를 고정했고 실제 청구·크레딧·디스크·네트워크 비용은 측정하지 않았다. [공식 VM 가격표](https://cloud.google.com/products/compute/pricing/general-purpose)의 지역별 가격 UI를 이번에 확정하지 못했으므로 비용 수치는 추정이다. 중첩 실행 비용을 합해서 할당 비용으로 보고하지 않는다.

## 거부·미완료

수정 전 분포와 후보 근거는 `rejection-before-*.json`, 최종 누적 관문·거부는 [rejection_table.json](rejection_table.json)에 둔다. N16 4SIM초에서 physics1439.078/loop1450.718초, 교사3.395초였다(공유 부하). 기본 off float32 tolerance A/B는 단일 초기 tick의7→4 iteration, physics10.878→10.183초뿐이어서 주원인 해결로 채택하지 않았다.

명시 sleep compact 후보는 pinned MJWarp의 NEVER/ALLOWED 미지원으로 HOST_ERROR였고 최종 CLI에서 제거했다. 자동 sleep 정책 전체의 미지원이라는 뜻은 아니다. 실제 서로 다른 seed 모델은 `dof_length` 차이를 배치할 수 없어 거부했다. 질량/기하/파생 모델 값을 근사하거나 버리지 않았다. 같은 모델별 cohort/지원 레이아웃을 먼저 해결해야 한다.

교사 상태기계·IK·가시 ray에는 세계별 루프가 남는다. 학습 recorder 승인 어댑터·ACT 학생 배치 평가·완전 GPU reset은 미완료다. 현재 장면의 반투명 구역은 Warp에서 불투명하게 보이며 C 바닥 패턴과 차이가 있다. 카메라 방향/광각/시작 위치는 몽타주로 확인했지만 관측 의미 동등성이나 이 차이의 실패 원인은 확정하지 않았다.

[교사 관문 대기열](teacher-gate-queue.json)은 **HOLD_SCENE / approved=false / executed=false**다. frozen source plan40개와 absolute rejection_table 경로를 연결했다. scenetex5 장면 선택·모델 hash·backend 부족분을 해결한 뒤 조정자가 승인해야 제출한다. 학습용 카메라 기록은 off이며 검토/10Hz terminal ring만 별도다.40개를 실행하지 않았다.

검토 영상·모든 프레임 띠는 gcp2에서 만들고 Mac 기본 checkout의 `outputs/e2e18-admin/playback/warp1-*`로만 회수한다. top overview는 평가용 상태에서 사후 재구성했으며 제어 입력이 아니다. 실제 자기 RGB와 분리 표시하고 r2는 solo 작업이라 N/A다. 영상은 ffprobe로 확인하며 화면 앱을 열지 않는다. 원본 전체는 VM에 있고 해시만 보존한 것은 백업이 아니다.


추가 기본 off 후보 `--native-sleep-policy-compat-v1`는 C3.16과 pinned MJWarp의 실행 predicate에 근거해 컴파일 뒤 NEVER/ALLOWED를 같은 의미의 AUTO_NEVER/AUTO_ALLOWED로 옮긴다(INIT 거부). package75개 Python 파일이 upstream57b4692f와 모두 같은지 git blob hash로 확인했다([환경](environment.json), [75파일 확인](mjw-source-verification.json)). package 자체는 변경하지 않았다. 실제 import52 active DoF, robot+target58→workspace64를 확인했고 N16의 서로 다른 시작/RGB3종과 reset10개 field도 통과했다. 같은 sleep XML의 C/L4 정성3개는3/3 완료했으며 이전 n4/C 코호트와 분리한다. 이 후보의 N1/N16 유한 정성과 N16/64/256 RGB prefix는 종료했다([최종 측정표](measured-results.md)). N1에는 의도적 pause가 포함돼 전체 wall을 처리량으로 쓰지 않는다. N16/64/256의 최신source90a25999·0.1SIM초 loop 처리량은0.14627/0.34219/0.57261SIM초/초, 초기화 포함 추정177.35/477.73/875.28SIM초/$다. C n4의 같은0.1SIM초 prefix는cold0.30528SIM초/초·349.44SIM초/$이며,4SIM초 prefix는cold3.43601·3933.11이다. 초기화·공유 부하·프로필 차이로 정상 상태의 우월성을 판정하지 않는다. compact의 upstream scaling `ctol/cls_tol/nvmax_pad`도 실제 값으로 기록하며 기존1e-8 결과와 합산하지 않는다.


고정0.1SIM초 제어 구간을 CUDA graph 횟수로 나눌 때 물리 tick을 버리지 않도록 정수 비율/GCD 검사를 넣었다. 현재 frozen timestep0.00025초는400tick=16×25로 기존 실행과 같다. 향후 별도 승인 모델의 timestep이 달라도 남은 tick을 잘라 .096초만 실행하면서 .1초로 보고하는 경로를 막는다. 이 변경은 timestep이나 성공 허용값을 바꾸지 않는다.

## 최종 원본·회수 확인

L4 실행 원본16,148파일의 SHA256 목록을 VM에 보존했고 완료 manifest 불일치0, 보고된 실행은 모두 terminal이다. 입력 감사739개에서 `invisible_measurements=0`, `held_world_reads=0`을 확인했다. 모든 수는 짧은 prefix·중단 포함이며 독립 성공 시드 수가 아니다. CPU/L4 원본 경로와 manifest 해시는 summary에 있다. 회수한 최종 JSON과3개 추가 검토 영상/프레임 띠24파일은 [해시 확인](retrieval-verification.json)을 통과했다. 전체 raw 백업은 아니다.

[영상 검토](playback-review.json)는 C 성공1, MJWarp 기본 N1 성공1, N16 prefix cap, native N1 성공/추가 시드 cap/N16 world0 성공의 전체2Hz·마지막10SIM초10Hz를 포함한다. 원인 분석이 가능한 완료 물리 실패는 없었으며 HOST_ERROR에 없는 행동 영상을 만들지 않았다. N16 나머지15세계는 결과·감사만 확인했고 전체 영상을 직접 검토했다고 표시하지 않는다. [대표 native N16 world0 영상](videos/warp1-native-mjwarp-n16-world0-8317100-3x.mp4)과 [메타데이터](video-native.json)를 보존한다.

L44시간 상한과 최종 임대/프로세스/VM 상태·전체 VM 시간대 추정 비용은 [operations](operations.json)·l4-stop-audit*.json에 기록한다. CPU는 다른 작업의 임대·프로세스 때문에 정지하지 않았다. 기본 checkout 소스·Git HEAD는 수정/업데이트하지 않았고 PR은 draft다.

L4 최종 상태는 **TERMINATED**다. VM 시작~정지 3.8366시간(<4h), 전체 공유 VM 시간대 추정 **$4.2049**(단가가정 $1.096/h, 실제 청구 아님). 정지 직전 임대0·관련 실행 프로세스0을 확인했다. 자체4h guard는 정지 확인 뒤 종료했다.
