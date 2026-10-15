# reloc18 — place 미도달과 시각 보정 수용

**NOT_READY.** 최대3라운드17회로 종료했다. place는 각 라운드 후보0/2이며,
모든 시드에서 명령 예측보다 나쁘지 않아야 한다는 기준도 미달이다.
기본 off 후보와 실패 근거를 보존한다. [DRAFT PR #538](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/538).
시작 소스 `47670d1428abfbb09756627c1a2be31caf650465` (reloc17 PR #536).
장면 `walls_floor_contrast_v5_indigo110_s80 + v1 floor + no_mip_v1` 고정.
gcp2 CPU만 사용, 자기 동시 ≤8, 임대 합계 ≤40, 최대 3라운드.
Mac 물리·렌더·GUI·모델 호출 없음. DEV 예산: 최대 24회×250 MB + 분석 1 GB = 7 GB.
원본은 gcp2 영속 디스크, Mac에는 요약·몽타주·실패 프레임·8 MB 이하 영상만 회수.

원본 대조: 위치 추정 시드 93584/93583에는 place 임무가 없다. reloc17의 place 0/2는
별도 운반 시드 93266/93315다. 두 코호트를 합치지 않고 분석한다. 존재하지 않는 place
프레임을 만들거나 전체 완료 성공 대신 부분구간을 성공으로 표시하지 않는다.

순서: 원장 관문·거부 표와 영상 직접 검토 → 명령만 장거리 기준 → 원본 잔차 공분산
보정 및 χ² innovation gate/Kalman 가중 융합 → 같은 시드 짝 비교. 정답은 평가·오프라인
보정계수 추정에만 사용하고 실행 입력에는 넣지 않는다. 후보 토글은 기본 off.

## 원본 원인 분리

기존 운반 10회 전부 final place-view/advance/lower/open 0회다. `place-table.md`에
최종 화물 구역 여유·위치 오차·종료 단계·사유별 분포를 나란히 기록했다.
이 자료에서는 구역 자세·높이·내려놓기 조건 자체가 실패 원인인지 시험되지 않았다.
가장 앞에서 막히는 곳은 위치 예산 → 내려놓기/재관측 → 재접근이다.

reloc17 R2 carry PF의 기존 오수용은 93266 yaw>5° **3/25**, 93315 **27/31**이다.
compass만의 0/58·0/39와 다른 관문이다. 93315 t94.2의 PF는 σxy 약2.1–2.2cm,
σyaw 약1.95°·cluster mass≈1로 잘못된 모드를 수용해 자기 추정 위치를1.24m/yaw77° 바꿨다.
실제 한 틱 이동은 약1mm다. 위치 오차가1.40m·yaw83.5°로 커진 뒤 재접근이 끝나지 않았다.
기본 off 후보는 이 PF 경로와 compass, 재관측 pose 갱신까지 관문/가중 융합에 연결한다.
운반 원본은 무하중 위치 추정과 다른 드리프트 분포이므로 별도 보정 파일을 쓴다.

`replay.json`은 동일 저장 명령열에서 command-only vs 후보의 **로컬** 오차다.
93584 xy 중앙/p95 .0405/.0691→.0312/.0445m,
93583 .0508/.1775→.0335/.1009m. 93583의20–40초 구간과93584 yaw p95는 악화한다。
전체 p50/p95 개선만으로 모든 시간 구간·yaw 또는 폐루프 개선으로 확대하지 않는다.

신규 R1 시각 기준선의 첫150 SIM초는 원본과 명령1500/1500개가 각 시드에서 정확히 같다
(`command-prefix.json`). R1 명령 대조2회는 pose 복원 시 fix-age 카운터가 복원되지 않는
계측 오류를 발견해 SIGINT로 종료·`INVALID_CONTROL.json`을 남겼다. 대조군 결과에서 제외하고
수정한 대조군을 R2에서 다시 쟀다. 원본과 실패 기록은 삭제하지 않았다.

영상·프레임: primary `outputs/e2e18-admin/playback/reloc18-{93266,93315}/`의 전체2Hz·마지막10초10Hz,
`reloc18-six/`의 각 변형6장씩16개 프레임 판을 회수했다. 위치 추정 시드의 프레임은
place 영상이 아닌 위치 추정 영상임을 manifest에 명시했다. 자세한 검토는 `playback-review.md`.

## 최종 place 진단

원래 command-only `.0382/.0488m`는 두 시드의 **중앙값**이다. 원본 로컬 중앙/p95는
93584 `.0382/.0956`, 93583 `.0488/.2256m`였다. 이 수치는 하중 운반 전역 오차가 아니다.

R3에는 두 운반 조건 모두 DEV pose-budget observe-only를 켰다. 불확실성 would-stop을
기록하며 경로·정상 물리·근거리 동작·place 판정을 유지한 별도 진단 조건이다.

|조건·시드|place-view|기하 통과|목적지 색 통과|처음 xy 오차 m|처음 site 구역 여유 m|
|---|---|---|---|---|---|
|보정93266|31프레임|31/31|0/31|2.3814|−2.0345|
|보정93315|31프레임|31/31|0/31|1.1916|−.7801|
|명령만93315|31프레임|31/31|0/31|.7285|−.6411|
|명령만93266|미도달|미검증|미검증|—|재관측 실패206.2초|

후보는 도착했다고 추정했으나 실제 구역 밖이었다. 93프레임 모두 목적지 색 비율0이고,
원래 gate와 저장 RGB 재구성93/93 일치다. `destination_floor_not_visible`가 막았다.
advance/lower/open/final place는0/2다. 색 임계값이나 카메라 기하 결함이라는 근거는 없고,
최종 높이·자세·내려놓기 동작은 아직 시험되지 않았다. site는 발행 PWM 명목 FK와 평가용
실제 base로 계산했으며 하중 처짐/실기 교정은 미확인이다.
[최종 표](final-place-table.md), [93프레임 원장](terminal/round3-place-predicates.json.zst).

실제 place 처음/중간/끝 두 장씩6장:
[보정93266](figures/reloc18-r3-carry-candidate-93266-133c12f4.jpg),
[보정93315](figures/reloc18-r3-carry-candidate-93315-133c12f4.jpg),
[명령만93315](figures/reloc18-r3-carry-command_only-93315-133c12f4.jpg).
[노출 시각·원본 해시](place-frames-manifest.json).

R2의 별도 setdown 거부는 `wall_divider_1` 추정 틈−.1388m였으나 같은15cm 후퇴를 실제
위치에 평가하면 정적 벽 여유+.7552m였다. 위치 오차 약1.32m로 생긴 거짓 벽 거부다.
동적 물체 여유를 포함한 계산은 아니다([평가 원장](setdown-gap-eval.json)).

## 보정 구현과 최종 비교

후보는 `S=P+R`, `NIS=νᵀS⁻¹ν`, χ² 관문과 Kalman gain/Joseph posterior를
PF·compass·full-pose 재관측에 연결했다. pose 자유도3/α=.01/11.3448667301,
heading 자유도1/α=.01/6.6348966010이다. 작은 P에서 시각 영향이 작아지는 검사를 포함했다.
무하중 R 바닥은 원본 잔차 p95/1.96, carry PF core는 모든69후보의 중앙 절대 잔차/Φ⁻¹(.75)로
맞췄으며 p95 꼬리도 보존했다. 정답으로 이상치를 삭제한 적합은 아니다.
관측 상관 시간만큼 솎고, 무하중/carry 분포를 분리했다.

R2의 누적 오차 Q는 초기 등록 오차와 과정 잡음을 혼합했고 PF120/120을 통과시켰다.
R3 Q는 원본 body 전이 잔차 p95와 양수 자기상관 합으로 적합하며 idle/moving을 분리했다.
R3 map→odom 보정은 연속 로컬 odometry를 유지하고 RGB 전역 측정을 한 번만 소비한다.
실행의 로컬 pose와 명령 적분 차이는 최대 약1.7e−14m다. 모든 적합은 같은 DEV 원본 기반이다.
가우스성·관측 독립성·새 시드 확률 보장은 미확인이고 명시적 mixture likelihood/편향 상태는 없다.

단위 m, 중앙/p95. 명령 대조는 **같은 후보가 실행한 명령열의 shadow**다.
별도 command-only 폐루프 실행은 원장에 따로 보존했으며 동일 궤적으로 가정하지 않는다.

|범위·시드|명령 예측|시각 보정|판정|
|---|---|---|---|
|R2 60초 로컬93584|.0466/.1176|.0420/.1019|로컬 개선, 전역 별도|
|R2 60초 로컬93583|.0495/.1410|.0412/.1146|로컬 개선, 전역 별도|
|R3 등록 후 전역93584|.0767/.1454|.0363/.0880|종료 전496표본 진단|
|R3 등록 후 전역93583|.1804/.2741|.0910/.1268|종료 전438표본 진단|
|R3 운반93266 143.9초|.8516/1.7628|.5101/2.3119|p95 악화|
|R3 운반93315 78.4초|.2104/1.1784|.1897/1.1535|xy 개선, yaw 중앙 악화|

R3 selfmap은115.4/103.4초에 `selfmap4_relocalization_exhausted`로 끝났다.
원래 status `HOST_ERROR`를 보존했다. VM 장애가 확인된 것은 아니며 재위치 추정 소진이다.
180초 완료/성공으로 세지 않는다. 전체 운반 계획 완료도0회다.

[시간 구간 표](drift-table.md): carry93266 명령 xy p95는 첫50초 .6489→100초 이후1.8505m,
93315는 첫50초 .4432→50초 이후1.2162m다. selfmap93583 명령 p95는 첫30초 .2007→60–90초
.2742m이며 보정은 .1111→.1283m다. 그러나 carry93266의100초 이후 보정 p95가2.3813m여서
긴 경로 문제는 해결되지 않았다.

R3 PF 원시 yaw>5°/수용은 carry93266 **8/14**, 93315 **0/3**이고 융합 뒤도8/14·0/3이다.
compass는0/114·0/0(수용 없음)이다. selfmap은 원시1/46·1/53, 융합 뒤0/46·0/53이다.
R3도 수치 χ² 거부0건이다. 공분산이 큰 상태에서 잘못된 모드가 gate 안에 남으므로,
χ² gate의 존재만으로 문제 해결을 주장하지 않는다. 다중 모드/편향/관측 가능성과 완주가 남았다.

## 실행·검증·보존

- R1 `a045584cf98c7ad0a723063c6afea2e6d43629f8`, R2 `46dd7ec3048a50a5443b2d61b0dece462e43b763`, R3 `133c12f4cbd5efafba5f94f761d494f45bef075a` 고정. R3 전 공유 브랜치 CI/부모 변경을 정상 병합했고 제어기·시뮬 코드 동일성을 확인했다. 실행 뒤는 분석·기록만 바꿨다.
- gcp2 n4-highcpu-64 C MuJoCo CPU, pool4·타 임대16+16 포함 최대36≤40. 모든 queue에 임대·자원·이전 rejection_table을 기록했다.
- 첫30초 wall/SIM 중앙값 R1/R2/R3 5.1851/4.8793/4.0951: 3.5 경고·6.0 차단 기준으로 통과했다.
- 4+7+6=17회 모두 종료. R1 계측 무효2회와 R2 사전 지정 실패-window1회를 채택 비교에서 제외했다. cap_end5(실패-window 포함), 무효 중단2, 재접근 실패1, 재위치 실패3, setdown 여유 거부1, 목적지 바닥 거부3, selfmap 소진2를 따로 기록했다.
- 원본17/17의 **29,623파일 SHA-256 불일치0**. invisible_measurements=0·held_world_reads=0은17/17 기록, selfmap4회의 top/truth 입력도0이다. [47개 비물리 검사](tests.md).
- [모든 실행 요약](summary.json), [순차 관문·거부 표](rejection-table.json), [원본 검증](terminal/integrity.json), [회수 검증](retrieval-final-media.json), [파생 자료 압축/해제 해시](terminal/manifest.json). 기존 큰 요약도 무손실 압축했다([compression.json](compression.json)).
- 각 raw 절대경로는 summary에 있다. 배치 `/home/ugrp/ugrp-sim/runs/reloc18-round{1,2,3}/`, 원본 총약510MiB. Mac은 fetch-lite만 회수했다. 모델 호출·학습·학생 실행0이며 VM에 모델 키/에이전트 자격 증명을 두지 않았다.
- [대표4배속 실패 영상](videos/representative-carry93315-r3-failure.mp4), 35,552bytes, SHA256 `c8470138b36d30370d36a4479b403853d2a5e3186ec260fa676f63d690c324fa`. 원본 R3 93315를 milestone로 표시해 영상과 데이터를 보존한다. 완주·학생·실물 성공 근거가 아니다.
- [직접 영상 프레임 검토](playback-review.md). 같은 조건 전체 성공 원본이 없어 성공1개 비교는 미충족이다. 새 실행 대기열 없음.
- [종료 확인](cleanup.json): 자체 워커0·reloc18 임대 제거. beampair9 임대와 다른 Python 작업17개가 있어 gcp2는 정지하지 않았다.

분석 재현은 gcp2의 frozen source를 PYTHONPATH로 지정해 `summarize.py --round 3`,
`selfmap_results.py <R3-source> 3`, `place_predicates.py`, `terminal_evidence.py <R3-source>`,
`report_terminal.py` 순서다. queue의 정확한 실행 command/environment는 별도 보존했다.
이번 제한을 넘어 새 물리 실행을 자동 제출하는 분석기는 없다.

후보 토글 `reloc18_innovation_v1`, `reloc18_map_odom_v1`, `reloc18_process_cov_v1`,
`reloc18_pose_budget_observe_only_v1`는 모두 기본 off다. 마지막은 DEV 진단이며 strict 관문/학습 자료가 아니다.
실패 직전10 SIM초 자기 RGB10Hz는 제어와 별도 기록 옵션으로 유지했다.

## 출처·미확인 범위

- [Piché 2016, DOI10.1002/acs.2571](https://onlinelibrary.wiley.com/doi/10.1002/acs.2571): NIS 정합성 시험 초록 확인, 유료 본문 식/절 **미확인**.
- Bar-Shalom, Li, Kirubarajan, *Estimation with Applications to Navigation and Tracking*, Wiley2001: 서지 확인, 책 본문/정확한 절 **미확인**.
- [Kalman 자동 조정 논문](https://arxiv.org/pdf/2306.07225): NIS/NEES와 χ²만으로 올바른 튜닝이 보장되지 않는 한계. Bayesian optimization **미실행**.
- [공식 Nav2 AMCL 파라미터](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/): sigma_hit와 hit/random 혼합·이동량 갱신. lidar 기본σ를 RGB pose에 복사하지 않았다. 원시 관측모델 전체 재최적화 **미실행**.
- [공식 REP105](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-0105.rst), [공식 AMCL map→odom 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/amcl_node.cpp): 연속 odom/전역 map 프레임 분리 참고.

식·상수 근거와 확인 범위는 [references.md](references.md), `configs/calibration/reloc18_*_v1.json`에 기록했다.
