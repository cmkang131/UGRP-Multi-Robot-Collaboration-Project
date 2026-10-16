# v387 저장 상태 단계 시험

실행 소스 SHA: `88a2a792bdfd61b606364a58bb9aeb6543c7adad` (이후 기록 고정 커밋과 구분).

2026-10-13 조정자 후속 지시에 따라 이 PR에서 직접 만들었다. `stage-request-v2.json`이 이전 540초/16회/어댑터 대기 계획을 대체한다. **정렬 상태 준비 4/4, 매핑 중간 상태 준비 1/1; 실제 시험 0/32, 핵심 부분집합 0/16. 파지 성공 수·시간, 물리 배치 오차, 실제 RGB 재생 일치, 기준선 재탐색 재현은 미확인이다.**

## 구현·범위

- `harness/e2e_stage_checkpoint.py`: cutoff 이전 자기 명령과 accepted own RGB 목록을 봉인한다. `ownmap.jsonl`의 당시 자기 위치·B·봉 추정과 재생 출력을 대조한다. 현재/미래 평가 좌표는 제어기에 전달하지 않는다. 최종 지도에서 노드를 잘라 쓰지 않는다(미래 loop correction 가능).
- `sim/e2e_stage_staging.py`: 기존 E2E 표준 `Scene`과 native 포트를 재사용한다. `pair_stage_probe.py`의 TEST_SETUP_GT 경계, `zone_pair_highpose_staging.own_history`, `pair_stage_probe.CRITERIA['grasp_lift']`를 재사용한다. GT 로봇 xyz/yaw와 봉 xy/yaw/COM-z는 초기 배치와 평가에만 쓴다. 정적 지도·로봇 XML/카메라·접촉 설정/봉 형상 지문을 원본과 대조한 뒤 배치 오차 각 축/각도 ≤1e-8 확인, weld OFF 확인, 새로 만든 상태의 `mjSTATE_INTEGRATION` NPZ 저장·복원 비트 일치를 검사한다.
- `scripts/run_e2e_stage_probe.py`: 기본 off `--enable-stage`, Linux만 허용. 기존 `make_robots`/`make_transport` 공통 factory, 동일 접근·시선·queue·clearance·pulse admission을 쓴다. 정렬 이후에는 grasp queue만 처리하며 운반/GO/ACK로 진행하지 않는다. 첫 새 관측부터 단계 cadence를 적용한다. 최대 **300 SIM초**, 1,800 wall초. 모델 호출 0, 공급자 비용 0(새 추론을 요청하지 않는 이 단계 실행에 한함).
- 매핑 진입도 `prepare --stage mapping --cutoff <SIM초>`로 지원한다. `mapping30` 예시를 포함했다. 매핑 실행은 자기 경로를 생성하면 종료하며 승인/발화/운반을 만들어내지 않는다. 경로 후보 제어 옵션은 route1 작업에서 이 공통 초기화 API에 적용한다.

가벼운 로그에는 원래 qvel/관절 실측/roll-pitch/적분 상태가 없다. **원본을 비트 단위 재개한 것이 아니다.** 초기 속도 0, yaw-only, 당시 발행한 팔 목표를 설정한 staged reproduction이다. 원본과의 관절·속도 오차는 측정할 수 없다. 새로 만든 물리 상태의 저장/복원 일치와 원본 r80 물리 재개를 구분한다.

원본 격자 전체 해시도 없다. 원본 JPEG를 재생해서 만든 격자·graph·자기 좌표 변환의 JSON 왕복 해시와 transport 인계 전후 해시가 같아야 한다. 당시 기록과는 모든 accepted frame의 자기 위치(최대 절대오차 1e-6)·B/봉 추정(정규 JSON 해시)을 대조한다. 이 재생은 서버 원본 RGB가 있어야 검증된다. Mac 회수본은 RGB가 없으므로 검증 완료라고 표시하지 않는다. 해시나 추정이 다르면 **HOST_ERROR로 물리 생성 전에 종료**하며, 허용 오차를 조용히 넓히지 않는다.

r80 source는 sensors-on 구성이나, 선택한 네 상태의 정렬 전 r1/r2/r3 **us_zero=0 (12/12)**이다. 이 조건을 preparation에서 검사해 과거 초음파 위치 보정을 누락하지 않도록 한다. 새 단계는 사용자 관측 경계에 따라 초음파 공급자를 연결하지 않는다. 따라서 비교는 **v375 제어기를 부모로 한 RGB-only v387 staged baseline**이며 원래 v375 전체 실행과 동일하다고 주장하지 않는다. 모든 후보에 같은 경계가 적용된다.

## 상태와 짝 비교

| 원본 장면 | 정렬 시작 SIM초 | 300초 내 acquisition 시작 r1/r2 | 최대 scan cycle r1/r2 |
|---|---:|---:|---:|
| v375 s61008 | 52.3 | 1 / 1 | 1 / 8 |
| v377 s61006 | 79.4 | 2 / 2 | 7 / 5 |
| v379 s61008 | 95.0 | 1 / 2 | 0 / 0 |
| v380 s61007 | 135.5 | 1 / 0 | 3 / 0 |

위는 회수한 실패 장면의 관측 종료까지 자료이며 완료시간/새 성공률이 아니다. 전환 누락·짧은 관측 때문에 cycle 0과 acquisition 0은 성공을 뜻하지 않는다. 상세 체류시간·검출 상실 시점·출처 해시는 `r80-stage-diagnostic.json.zst`에 있다.

4조건(v375/v384/v385/v386) × 4상태 × seed 62001/62002 = **32회, seed별 16개씩 두 묶음**이다. 각 조건 8회, s61008 원본 두 장면 핵심 부분집합 전체16회/조건별4회. 과거 자기 지도/RNG 재생은 원본 seed로 고정한다. 반복 seed는 새 물리 생성기에만 적용한다. 반복이 같으면 독립 궤적으로 세지 않고 보고한다.

스테이징에서 새 모델 호출 없이 건너뛴 구간은 mapping/dialogue이며, 정렬 진입 자체를 TEST_SETUP으로 표시한다. 과거 승인을 재발행하지 않는다. `held`는 기존 grasp_lift 기준인 양 로봇 양쪽 집게 접촉·3cm 상승·기울기10도 이하와 발행한 집게 닫힘을 0.30초 유지한 평가 라벨이다. 접촉 힘은 양수여야 한다. 바닥에서 닿기만 한 것을 파지 완료로 세지 않는다. 실제 로봇 실험이나 운반 성공 판정이 아니다.

첫 시도 지표는 더 엄격하게 **정렬 진입 뒤 acquisition 시작이 0인 파지 성공**으로 정의한다(초기 검색도 포함). 시작 횟수, 실제 관측된 scan cycle 증가수, 각 로봇 held 시각·차이, 성공 실행 시간 중앙/최대, censor/HOST_ERROR를 함께 보고한다. 기준선은 장면·seed별 acquisition 재발 여부를 먼저 확인하며, 재현되지 않으면 그 짝은 원인 개선 근거로 채택하지 않는다. 원본 궤적 동등성 검증이 아니다.

## 감독자 실행

1. 이 PR의 지정한 커밋을 별도 서버 실행 소스로 고정한다. `R80_ROOT`는 보존된 원본의 부모 디렉터리(각 `<run>/raw` 아래 JPEG 포함), `RUN_ROOT`는 새 영속 디스크 경로다. 원본이 아카이브에만 있으면 체크포인트의 `own_inputs[*].frames[*].path`에 나열된 prefix JPEG만 복원할 수 있다. `--raw`는 RGB 파일을 읽는 곳이며 준비된 체크포인트가 명령·추정 prefix를 포함한다.
2. 조정자가 잔액 확인; 감독자는 VM3 한 대, 동시16개와 전체 남은 쓰기를 합친 디스크 예산·여유를 확인한다. 예상 본시험48GiB + 30초 게이트 약4.8GiB(미측정 상한 가정), Mac은 경량0.32GiB만 회수한다. 새 제어 루프에 모델 호출은 없다.
3. `stage-request-v2.json`의 첫 seed 16개 argv를 **인수 배열로** 실행한다. `${R80_ROOT}`, `${RUN_ROOT}`, `${SOURCE_SHA}`는 감독자가 실제 값으로 치환한다. 먼저 cap30, 별도 출력 이름/배치에서 계획 동시16개로 30SIM초 게이트(중앙 physics_wall/SIM≤3.5, 16개 모두 완료)를 확인한다. 재생/초기화 wall은 따로 기록한다. 게이트 초과/복원 실패는 본시험을 시작하지 않고 자료를 회수한다.
4. 통과하면 cap300의 두 묶음을 실행한다. 첫 묶음 baseline 재탐색 결과가 r80와 맞는지 확인하고 다음 묶음을 판단한다. 같은 checkpoint×seed의 네 조건은 같이 실행한다. 종료 뒤 기존 `compress_json_traces.py`로 >64KiB JSON을 SHA 검증 압축한다(원본 r80 자료는 이 작업에서 변경하지 않는다).
5. 결과는 `python -m scripts.summarize_e2e_stage_probe --matrix experiments/2026-10-13-e2e18-grasp1/stage-request-v2.json --result <result.json> ... --output <새 요약.json>`로 정리한다. 예상32개, 누락, HOST_ERROR, 핵심16개, 조건별/짝별 결과를 따로 남긴다. 시간 차이는 소스·초기 물리·자기 지도 해시가 같고 둘 다 성공한 짝만 계산한다.

예시(prepare는 물리 실행 아님):

```sh
python -m scripts.run_e2e_stage_probe prepare --raw "$R80_ROOT/e2e18-v375-s61008-r80/raw" --stage mapping --cutoff 30 --output outputs/route-entry.json.zst
```

실행 등록은 `configs/simulation_workflows.d/e2e18_v387.json`이다. main과 열린 PR 9개 전체의 RUNNABLE_ID/workflow 최대386을 확인하고 #475에387 예약을 알렸다. v387은 staged 실행 래퍼이며 후보 번호384–386을 덮어쓰지 않는다.

## 참고 자료

- [MuJoCo Simulation / State and control](https://mujoco.readthedocs.io/en/3.3.0/programming/simulation.html): 공식 문서 확인. 위치뿐 아니라 속도·activation·solver warm-start 등이 재개 동등성에 영향을 준다. `mj_getState`/`mj_setState`와 `mj_forward`를 이용한 새 staged integration 저장·왕복 검사를 적용했다. 이 문서가 가벼운 r80 로그로 완전 복원을 보장하는 것은 아니다.
- 저장소 `harness/pair_stage_probe.py`, `harness/zone_pair_highpose_staging.py`, `scripts/run_pair_stage_probes.py`의 기존 staging/평가 경계와 저장 방식을 확인·재사용했다.
- 시선 제어·추적·Nav2 docking의 표준/공개 코드 및 최신 논문 조사와 채택/미확인 구분은 같은 폴더 README의 참고 자료 절에 유지한다. 이번 공식 Nav2 튜토리얼 URL 재조회는 오류였으며 새 근거로 추가하지 않았다.

최종 로컬 검증: 관련3파일 **35/35 통과**. CI 목록 등록 및 표준 관리 CLI plan 확인. 물리/렌더 실행과 실제 원본 RGB 복원은 이 결과에 포함하지 않는다.
