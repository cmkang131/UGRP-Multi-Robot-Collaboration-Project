# reloc11 — 질감 API·특징·속도 개선, 정적 등록 BLOCKED

**직접 GCP 2라운드7회를 실행·회수·해시 검증했으나 정적 등록은 모든 실행에서0이다.** 3라운드는 예정된 VM 정지로 소스 전송만 실패했고 시뮬레이션0회다. 재시작한 공유 VM의 상한이 외부 작업에 의해24시간으로 바뀌어 이 작업의8시간 조건과 달라 추가 제출을 중단했다. 비용 정지 발동 기록은 없다. 3라운드를 실행 완료로 세지 않는다.

질감은 자기 카메라 위치 추정의 주 장면이며 smooth는93571 기준1회만 측정했다. 장면·주기·소스·호스트·모형 결과를 합산하지 않는다. 아래 분모는 각 실행의 시간상 상관된 프레임이며 독립 임무 성공률이 아니다.

## 변경과 보존 판단

- 이전 미push 병합 `4b1ab996`은 origin/main `e3d5149b`와 PR511 `db0a6858`을 포함한다. 남아 있던3개 미커밋 수정(`sim/own_map_closed_loop.py`, `sim/solo_cyan_v106.py`, `sim/wall_parallax_strafe.py`)은 공식 API 연결 방향이 맞아 보존·계속 사용했다. 판단 없이 버리지 않았다.
- 복제 질감/전역 scene factory 교체를 없애고 `render_profile_selection.for_name()`·공식 nearclip `audit(model, base_profile=...)`를 쓴다. 기존 PR511 이미지·manifest·재질만 사용했고 마찰/물리·카메라/FOV·색 인식 범위·인공 마커를 수정하지 않았다. 질감 backend는 R1/R2 모든 실행에서 제어 루프에 진입하고 compiled render/nearclip 감사를 통과했다.
- 새 옵션은 모두 기본off다: `--reloc11-timing-v1`(시간 분리), `--reloc11-half-rate-v1`(5Hz 진단), `--reloc11-low-contrast-v1`(FAST7), `--reloc11-wall-field-v1`(기존 AMCL 벽 거리장 비교). 끄면 기존10Hz·FAST20·joint PF 경로다. 정답은 저장 원장의 평가에만 사용했다.
- 5Hz는 별도 진단 조건이며 선정 주기의 모든 JPEG·원장·제어 입력을 보존한다. 학생 학습 데이터/ACT 주기·행동 동등성의 근거가 아니다. LK 간격0.2초는 기존 허용0.25초 안이다.
- 저대비 추출은 ORB-SLAM 공식 설정20/7 중 낮은7을 OpenCV ORB에 적용한다. 기존800개 상한·최소매칭8/인라이어6/전역12·SE(2)·공분산·독립시점/다중해 관문을 유지했다. ORB-SLAM의 셀별 fallback·분배나 전체 SLAM 구현은 아니다.
- 벽 모형은 PR507 정식 `static_walls_v1` AMCL likelihood-field를 선택한다. 자기 RGB 벽-바닥 교선만 PF 측정에 쓰고 색 선분 likelihood 곱을 제외하며, 색 지도는 기존 독립 기하/다중해 관문에 계속 쓴다.2000입자·기준은 유지했다. **단위시험만 통과했고 GCP 비교는 미실행**이다.

## 실행별 원본 재계산

전부 gcp1 / ugrp-act-train-1014 / n4-highcpu-64, dev PR506,90 SIM초 상한이다. 원본 상세는 [R1](round1.json), [R2](round2.json), 정확한 argv·제출 전 동시 수는 [명령](gcp-commands.json), 모든 상태는 [요약 JSON](summary.json)에 있다.

|조건·seed|소스|프레임|특징/매칭/인라이어 중앙|정적 특징 중앙|PF 해결|등록|종료|
|---|---|---:|---|---:|---:|---:|---|
|R1 smooth10Hz 93571|`4d3335c8`|456|34/4/0|4|341|0|HOST_ERROR 45.5s|
|R1 texture10Hz 93571|`4d3335c8`|901|16/2/0|4|756|0|RECORDED 90s|
|R1 texture10Hz 93581|`4d3335c8`|901|11/1/0|4|851|0|RECORDED 90s|
|R1 texture10Hz 93582|`4d3335c8`|480|27.5/3/0|4|326|0|HOST_ERROR 47.9s|
|R2 texture5Hz+FAST7 93571|`41c0104b`|430|191.5/11/0|4|313|0|HOST_ERROR 85.8s|
|R2 texture5Hz+FAST7 93583|`41c0104b`|322|173/13/8|4|245|0|HOST_ERROR 64.2s|
|R2 texture5Hz+FAST7 93584|`8c7586c0`|451|174/9/0|4|365|0|RECORDED 90s|

RECORDED 3개도 시간 상한까지 기록했다는 뜻이며 정적 등록/지도 완성 성공이 아니다. HOST_ERROR 4개은 기존 유한 재지역화 예산 소진이며 제외하지 않았다. R2 세 번째는 로컬 dirty-source 검사로 한 번 제출이 거절됐다(원격0회). 파일을 커밋해 `8c7586c0`로 제출했고 앞선 `41c0104b`와 실행 모듈9개 바이트 동일성을 확인했다([근거](runtime-equivalence.json), [실패](r2-local-submission-failure.json)).

공통 첫30 SIM초의93571만 비교하면 다음과 같다. 5Hz 행은151프레임,10Hz 행은301프레임이다.

|조건|특징 중앙|매칭 중앙|인라이어 중앙|등록|wall/SIM|
|---|---:|---:|---:|---:|---:|
|smooth10Hz|34|3|0|0/301|6.983|
|texture10Hz|32|4|0|0/301|6.820|
|texture5Hz+FAST7|275|14|13|0/151|4.005|

## 평가 전용 오차와 남은 원인

|조건·seed|PF 해결 프레임 위치 중앙(m)|yaw 중앙(도)|10cm/5도 안|
|---|---:|---:|---:|
|R1 smooth 93571|1.0301|2.510|0/341|
|R1 texture 93571|0.1058|0.906|262/756|
|R1 texture 93581|0.1218|7.527|107/851|
|R1 texture 93582|0.1006|3.389|99/326|
|R2 texture+FAST7 93571|0.1060|3.266|116/313|
|R2 texture+FAST7 93583|0.0646|0.917|204/245|
|R2 texture+FAST7 93584|0.0952|0.491|201/365|

질감·FAST7로 자연 특징은 늘었지만 정적 특징은 주로4개다. R2 93571의 전체430프레임에서 xy공분산 기각421, yaw공분산426, 센서 미갱신314, 기하113이었다(중복 집계). 다중해는 상류 미통과429회와 실제 평가 기각1회를 구분한다. R2 93583은 PF 평가 위치 중앙6.46cm·204/245프레임이10cm/5도 안인데도 yaw공분산322/322·xy321/322 때문에 등록0이다. 자연 특징 부족만으로 남은 실패를 설명할 수 없다. 평가 정답으로 공분산/관문을 낮추거나 통과시키지 않았다. R2 93571 yaw 오차 p90은21.87도여서 특징 증가만으로 정확도 개선을 보장하지도 않는다.

## 속도·검증 범위

R1 첫30초 wall/SIM은 smooth6.983, texture6.820/6.501/6.748이다. 질감93571에서 특징 추출1.923s, 추적2.193s, PF2.478s(2000입자), 구조 추출21.777s, 등록19.088s, 전체 제어100.711s, capture33.302s, 물리64.564s를 기록했다. 등록은 PF를, 제어는 앞의 계산을 포함하므로 중첩 시간을 더하지 않는다. PF 입자 축소가 주 병목 해결책이라는 근거는 없다.
R2 첫30초는4.005/3.920/4.524(중앙4.005, 모두6.0 미만)다. 제출 직전 전체 동시 수는 R1 3–17개, R2 1–2개로 달라5Hz 단독 효과로 해석하지 않는다. 선택한5Hz+FAST7 조건에서 통과한 실측 범위다.3.5 초과 경고는 남는다.
관련 단위시험은 최종 조합62통과·8제외, carry 인수 오염 회귀1통과(총63개 고유 통과)다. Mac에서 MuJoCo import를 차단했고 물리/렌더0이다. 제외8개는 MuJoCo 정의를 import하는 XML builder 시험이다. 초기 강한 차단기가 이8개를 setup error로 막았고, 최종에는 명시적 제외로 기록했다. CI에 새 시험을 등록했으며 전체 CI는 로컬에서 실행하지 않았다([검증](validation.json)).
모든 실행의 실제 입력 감사 invisible_measurements/held_world_reads는0/0, top RGB 입력0이고 TOP 파일도0이다. 저장 원본으로 시간/프레임/오차를 다시 셌다.7회 각각 자기 RGB6장, 총42장을 직접 확인했다([영상 색인·원본 해시](review.json), [검토 그림](review/)). 바닥 질감은 보이나 벽은 낮은 대비로 남는다. 원본 전체는 GCP 영속 디스크에 있고 Mac에는 텍스트 전체와 선택6장씩만 회수했다. 전체 RGB 백업 완료를 뜻하지 않는다. 재시작 뒤에도 VM SHA256SUMS7/7을 다시 확인했다([최종 상태](gcp-final-state.json)).

## 실행 중단과 대기열

3라운드93571 소스 전송 중19:03:54 KST에 `deferredStop`이 발생했다. 이후 외부 작업이19:04:14 KST에 `maxRunDuration=86400`(24h)·STOP으로 변경하고 재시작했다([이벤트](r3-vm-events.json), [상태](r3-vm-safety.json)). 이 작업의8h 조건과 달라 재제출하지 않았다. 비용 함수는 ACTIVE, 최신 costAmount0KRW이며 budget-stop 발동은 확인되지 않았다. **실행0·실패 제출1·신규93585/93586 미제출**이다. RGB0이라6장 검토는 불가능하다([R3](round3-not-started.json)). 이 작업이 보호 설정을 변경하거나 다른 호스트로 넘기지 않았다. 자기 실행 프로세스/임대는 모두0이며, 공유 VM과 다른 작업의 임대는 그대로 두었다.
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-selfmap9-8e5a0a82.json`:93571 먼저+신규93590–93593, 전부texture, max_parallel16, 모든 승인/실행 플래그false, **BLOCKED**. smooth93571은 이미 측정한1회만 참조한다. 실행 소스는 검증된 R2와9개 실행 파일이 동일하며 wall-field 옵션은 끈 계획이다. 등록0과 공유 호스트 상한 불일치를 해소하기 전 제출하지 않는다.
carry는 “추가로 carry worktree에도 연결”과 “이 worktree/대기열 밖 수정 금지”가 충돌해 경로 확인을 요청했으나 답변이 없어 적용하지 않았다. 공식 API 패치3개 파일은 `git apply --check`를 통과했다.22개 장면 계획과 회전 점검+재현3×2후보+신규8×2후보의23개 **BLOCKED** 큐를 준비했다. 후보는rotation/rotation_wall_search, 실행 플래그는전부false, 기존 smooth의 성공/회수/운영 메타데이터는 제거했다. 큐는 `20261015-solo-carry-tex-987d033f.json`이며 실제 새 carry 소스 커밋 뒤 반드시 재생성해야 한다. carry worktree/기존 실행/기존 큐는 이 작업이 수정하지 않았다. 별도 소유자가 기존987d033f를 재탐색/재관측 반복 결함으로 중단한 사실도 차단 근거에 남겼다([인수 기록](carry-handoff.json), [동시 상태](carry-concurrent-status.json), [패치](carry-texture-api.patch)).

## 재현 명령

다음은 저장 원본 재집계이며 시뮬레이션을 시작하지 않는다. 실행 argv는 [gcp-commands.json](gcp-commands.json)에 보존했다. 현 BLOCKED 대기열을 실행 명령으로 해석하지 않는다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python scripts/analyze_reloc11_selfmap.py \
  outputs/gcp1-runs/reloc11-r2-* --output outputs/reloc11/round2-reproduced.json
```

## 참고 자료

- [PR511·공식 질감 API](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/511), 병합db0a6858; 고정 자산과 material-only 회귀를 재사용했다.
- reloc10 원본: `/Users/changmin/projects/ugrp-wt/map-carry-zone/experiments/2026-10-15-reloc10/README.md`, `registration-diagnostics.json`, `original-diagnosis.json`.
- [Mur-Artal et al., ORB-SLAM, IEEE T-RO2015](https://arxiv.org/abs/1502.00956): 추적·키프레임·재지역화 원문.
- [ORB-SLAM2 공식 TUM1 설정](https://github.com/raulmur/ORB_SLAM2/blob/master/Examples/Monocular/TUM1.yaml): 저대비 FAST20/7과 설명을 확인(2026-10-15). 카메라 보정값은 사용하지 않았다.
- [Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/):6.4 likelihood-field의 도서 출처. 이번 웹 열람은 출판사 소개이며 본문 전체를 새로 열람했다는 뜻은 아니다.
- [Nav2 AMCL likelihood-field 공식 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp): 거리장·hit/random 혼합과 score 누적을 확인. RGB 교선의 잡음이 거리 센서와 같다는 보장은 없다.
