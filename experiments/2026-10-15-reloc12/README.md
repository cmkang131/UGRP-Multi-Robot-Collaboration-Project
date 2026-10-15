# reloc12 — 정적 등록 0건 해소, 운용 승격 NOT_READY

질감 RANSAC 후보는 **4/4회 첫 정적 등록**을 만들었고 첫 등록의 평가 오등록은 **0/4(10cm/5도)**다. 다만 등록 후 제어 자세의 기준 초과가 **147/446프레임**이고, 등록된446프레임 모두 `pose_uncertain`으로 지도 삽입이 막혔다. 네 실행은43.4–46.6 SIM초에 기존 재지역화 예산을 소진했다. 정적 등록 성공·후속 자기 위치 추정·지도 탐색·운반 성공을 구분한다. 새 selfmap/carry 큐는 **BLOCKED**, 물리 관문/학습은 제출하지 않았다.

시작 `3c4af5b3a8131d4d1154a47719af5aa9792bfdf4`, R2 실행 소스 `ff1ccf27a43fe73d9b49dac82caf26a4584060d0`. [전체 요약](summary.json), [실행별 원장](runs.json), [정확한 명령·동시 수](gcp-commands.json).

## 수정과 입력 경계

수정 전에 GCP 원본7회·3940프레임·PF 갱신628회를 다시 집계했다([거부 분포](rejection-distribution.md), [원장](baseline-rejections.json)). 신뢰도 판정에 확대 공분산을 적용하는 경로를 먼저 수정했다.

- `reloc12_raw_cov_gate_v1`: 신뢰도15cm/5도 관문만 PF 원 공분산으로 판단한다. 선 NIS·`registration_hypotheses`·반환 공분산은 기존 확대값을 유지한다. 기본off.
- `reloc12_ransac_hypotheses_v1`: 두 번째 독립 후보다. 여러 시작 선 쌍, 최소3개/70% 인라이어·두 축·지도 선2개, 인라이어 합의 재적합을 사용한다. 결정적인 최대16개 생성 선·4096개 제안·제안당3회 재적합이다. 두 해 또는 예산 소진은 거부한다. 유한 표본의 유일성은 연속 전역 유일성 증명이 아니다. 기본off.
- 계산은 새 PF 갱신 때 수행하고 사이 프레임은 자기 발행 명령으로 후보를 전파한다. stale 프레임은 등록 확인 수를 늘리지 않는다. 실제 버퍼 선 전체·현재 선·자기 명령 오도메트리·두 공분산을 trace에 보존한다.
- `reloc12_carry_reacquire_v1`: 화물 재탐색 중에도 위치 예산을 검사해 접근 복귀 전에 재관측한다. 같은 탐색 객체와 진행량을 보존해 이어가며, 재관측 회전은 탐색 진행량으로 세지 않는다. 순수 재탐색 회전10도 이상도 정체 판정의 진행 근거로 기록한다. 기존16도 복구/20도 상한과 새 가시 측정 요구를 유지한다. 기본off. 재관측을 제외한 탐색·계획 예산은 검사 수 또는 SIM 시간이다.
- 이 브랜치에 없던 carry 실행 의존성은 중단 소스 `987d033f28b40aa6182c1cde0dff2982e1d546d6`에서 필요한 모듈만 가져왔다([출처](carry-source-provenance.json)). 기존 공통 소스는 보존했고, 필요한 기존 `proportional_drive` 함수만 같은 바이트로 연결했다. reloc11의 공식 질감 API/nearclip 감사 패치를 검토·적용했다. 다른 carry worktree와 기존 대기열은 수정하지 않았다.

제어 입력은 자기 RGB·자기 명령·허용 정적 지도다. NIS와 다중해 검사에 평가 정답을 넣지 않는다. 정답은 아래 오차 집계에만 사용했다. 시간 상한 종료는 `cap_end`로 구분한다. 거부 원장에는 범주·막은 대상·최소 틈을 기록하며 위치 추정 관문처럼 물리 틈이 없는 경우 null과 `not_applicable`을 명시한다. carry 경로 거부의 틈은101개 직선 표본의 진단값이며 우회 불가의 증명이 아니다.

## GCP 2라운드, 질감5회 + smooth1회

전부 gcp1 / ugrp-act-train-1014 / n4-highcpu-64,5Hz+FAST7,90 SIM초 상한이다. 장면·후보·소스가 다른 결과를 합산하지 않는다. R2 내부 프레임도 시간상 상관된 값이며 독립 임무 성공률이 아니다.

|후보·장면·seed|소스|프레임|등록 프레임|첫 등록 평가오차|종료|
|---|---|---:|---:|---|---|
|R1 raw·texture93571|`eff716cb`|430|0|해 없음78/78|HOST_ERROR85.8s|
|R1 raw·smooth93571|`a82bc72e`|451|0|해 없음83/83|cap_end90s|
|R2 RANSAC·texture93571|`ff1ccf27`|220|82|3.49cm/0.10도|HOST_ERROR43.8s|
|R2 RANSAC·texture93583|`ff1ccf27`|218|133|9.85cm/2.48도|HOST_ERROR43.4s|
|R2 RANSAC·texture93584|`ff1ccf27`|234|147|8.72cm/1.56도|HOST_ERROR46.6s|
|R2 RANSAC·texture93585|`ff1ccf27`|220|84|5.26cm/0.52도|HOST_ERROR43.8s|

smooth 저장 버퍼83개의 GCP 오프라인 RANSAC 재생은 후보0개57·2개8·유일 후보18이었다. 유일 후보18개도 PF 자세와15cm/10도 안에서 맞는 것이0개여서 최종 등록 허용0이다([재생 원장](smooth-ransac-replay.json)). 즉 다중해/무해 검사와 PF 일치 검사가 나눠 막았으며 유일해 검사 하나만의 효과로 보고하지 않는다. 이는 저장된 smooth 궤적의 재생이고 새 smooth 물리 실행은 아니다.

R1 질감에서는 새 센서116→PF 해결95→원 공분산95→기하78→유일해0으로 막혔다. 따라서 공분산만 바꾸는 첫 후보는 부족하다. R2는 유일 후보·세 시점 확인을 거쳐 네 번 모두 등록했다. 관문별 개별/누적 통과 수·확인 길이 분포·유일해 후보 수 분포·오류는 [실행별 JSON](runs.json)에 있다.

R1 첫30 SIM초 wall/SIM은 texture3.122, smooth3.540. R2는4.460/4.034/4.480/4.183, 중앙4.321이다.6.0 미만이며3.5 초과 경고는 유지한다. 제출 직전 전체 MuJoCo 로드 프로세스는0–5개였다. 타 작업 예약을 포함해 보수적으로 중복 계산한 입장 상한은30–37개였고 전체40을 넘지 않았다. 이전 reloc11의6.98/6.82와 동시 부하가 달라 특정 변경의 단독 속도 효과로 해석하지 않는다. [검증·동시 수](validation.json).

새 실행6회에서 실제 전달 입력 감사는 모두 invisible_measurements/held_world_reads0/0, TOP0이다. 모델0, weld OFF. 다섯 HOST_ERROR는 실행기가 `selfmap4_relocalization_exhausted`로 기록한 제어 예산 소진이며 외부 호스트 장애/물리 성공으로 바꾸어 세지 않는다. smooth의 RECORDED도 cap_end이며 지도 완성이 아니다. 요청한 질감5회·smooth1회 범위에서 두 라운드를 마쳤고 세 번째 물리 라운드는 제출하지 않았다.

## 남은 결함과 새 큐

`harness/selfmap4_geometry.py:358`은 등록 뒤에도 `R@cov@R.T`의 확대 공분산을 실행 자세에 반환한다. 이어 `harness/self_map_integration.py:555`의15cm/5도 지도 삽입 관문이 등록446프레임 전부를 `pose_uncertain`으로 막는다. 실제 제어 표준편차의 실행별 최솟값도 xy19.7–22.7cm, yaw7.6–10.2도다([GCP 재집계](post-registration-blockers.json)). 이 공분산 용도 연결의 수정·새 물리 검증이 남는다. 이번에 지시된 선 NIS·다중해의 확대값을 임의로 낮추지 않았다.

첫 등록0/4 오등록과 등록 후147/446 제어 자세 오류는 다른 지표다. 제어 자세는 당시 실제 출력 pose를 지도 변환한 값으로 평가했고, 명령 오도메트리 투영 오차도 별도 보존했다. 이 값들을 서로 바꾸어 정확도를 보고하지 않는다.

[새 selfmap 큐](queues/20261015-reloc12-selfmap-ff1ccf27.json)5회, [새 carry 질감 큐](queues/20261015-reloc12-carry-texture-ff1ccf27.json)22회를 별도 생성했다. 같은 파일은 기본 프로젝트 `outputs/e2e18-admin/vm3-queue/`에 있다. exact clean source는 `/Users/changmin/projects/ugrp-wt/map-selfmap/outputs/reloc12/source-ff1ccf27`이다. source_sha40자리, 실패93571/93266 우선, max_parallel16/전체40,24h STOP·유휴20분·budget-stop 유지다. 모든 실행/승인 플래그false, 기존 selfmap9/carry-tex 큐는 사용하지 않는다.

이번 큐의 보수적인 DEV 승격 판단(조정자 설계)은 첫 등록 오등록0, 등록 후 제어 오류5% 이하, HOST_ERROR 없음과 첫30초 속도 중앙≤6이다. 사용자가 별도로 정한 오등록률 수치라는 뜻이 아니다. 현재 오류33%와 HOST_ERROR 때문에 **BLOCKED**다. carry의 반복 연결은 단위 회귀로만 확인했고 새 물리 재현93266·carry 관문·학습은0회다.

## 검증·원본 보존

Mac에서 MuJoCo import를 차단한 관련 검사58개 통과, 제외0, 물리/렌더0이다([로그](pytest-final.txt), [검증](validation.json)). 실제 소스·새 버퍼 재생·첫 이상 선 허용·반복 방 다중해 거부·예산 소진 거부·carry 접근 전 복구·동일 탐색 재개·진행 판정·큐 차단·평가 분리 회귀를 포함한다. 전체 CI는 로컬에서 실행하지 않았다.

GCP 전체 원본 manifest6/6 검증([원본 위치/해시](integrity.json)). 실행마다 자기 RGB6장, 총36장을 직접 검토했다([몽타주](review/), [원본 프레임 해시](local-review-verification.json)). 질감 장면의 바닥 특징·벽/문/구역 경계는 보이고 벽 대비는 낮다. Mac에는 요약·몽타주·선택 원본36장만 가져왔고 trace/전체 영상은 가져오지 않았다. 원본 전체는 GCP 영속 디스크에 있으며 별도 전체 백업 완료는 아니다. 기존 자료는 삭제하지 않았다.

재현 명령(물리 실행 없음):

```sh
PYTHONPATH=.:tests /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-10-15-reloc12/run_offline_tests.py -q \
  tests/test_reloc12.py tests/test_selfmap4.py tests/test_selfmap5.py \
  tests/test_selfmap6.py tests/test_reloc11_timing.py
# GCP exact source cwd + PYTHONPATH=.에서 최신 저장 분석 스크립트로 runs/reloc12-*를 재집계한다.
```

자기 물리 실행 PID·임대·예약은 모두0으로 정리했다([영수증](release-receipt.json)). smooth 오프라인 분석도 완료·회수했다. 공유 VM과 다른 작업은 유지했고24h·비용·유휴 가드는 변경하지 않았다([호스트 상태](host-safety.json)).
