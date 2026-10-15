# Solo map carry5 — 재확인·주행·장애물 결함 일괄 수정

PR #505 / `claude/map-carry-zone`, 기준 `870c0c59f3c2eae556abaa809ac1eddf33dce5ca`.
새 `carry5_active_localization_v1`은 기본 off다. 이전 프로필·결과와 합산하지 않는다.
이 파일이 들어간 최종 커밋을 push하고, 별도 로컬 대기열에 전체 SHA를 고정한다.
이번에는 원격 접속·시뮬레이션·렌더·모델 호출·학습·실행 제출을 하지 않았다.

## 근거 A·B·C 확인

- `carry3.md`, `carry4.md`, 사용자 지정 `.../scratchpad/carry4_review.md` 전문과
  `outputs/e2e18-admin/analysis/odometry-scale/report.md`를 읽었다.
- 93220의 **0·11·21·32·42·53 SIM초 자기 영상 6장**과 같은 시각의 평가용 top 6장을
  기존 몽타주에서 직접 봤다. 21–53초에 cyan 상자와 주변 영상이 거의 바뀌지 않는다.
  top 시야 밖의 작업 로봇을 top 영상으로 위치 확정하지 않았다.
  파일·SHA는 `carry5-frame-review.json`. 자기 검토 영상은 320×240 축소본이다.
  네이티브 640×480 검출기에 확대 입력하지 않았으며 실제 장애물 검출 정확도는 미측정이다.
- 원본 요약의 20.8초 이후 정지, 명령/실제 1.435/1.069m·최대 0.616m 오차는
  기존 진단의 측정이다. 이번 저장 입력 재현은 `.zst` 원장 **537틱**을 읽었다.
  21/30/53.6초 A*는 **정적 벽만: 경로 없음 3/3, RGB 원반만: 경로 있음 3/3**을 재확인했다.
  평가 정답 자세 반사실은 기존 근거 A에만 있으며 이번 제어 재현에는 넣지 않았다.
- 같은 저장 명령을 carry5 경보 조건으로 재생하면 **10.7초**에 먼저 정지·재관측 요청을 낸다.
  이때 yaw 예산 16.13°이고 하드 가드는 열려 있다. 이후 원장 재생은 옛 명령의 분석이며
  새 정책의 폐루프 결과가 아니다. 미래 RGB나 성공한 fix를 만들어 넣지 않았다.

## 변경

1. **재확인 단계:** 마지막 수용 fix 이후 예산이 0.40m 또는 16°에 닿으면 멈춘다.
   기존 하드 한도 **0.50m/20°**, 오차 계수 **25% / 25% / 0.10rad/m**는 완화하지 않았다.
   경로가 없을 때도 `pickup_no_route` / `carry_no_route`로 같은 재관측 단계에 들어간다.
   과제·스킬 시작이나 단순 RGB 수신으로 예산을 지우지 않는다. 실제 수용된 fix만 거리·회전을
   0으로 만들며 그 이후 공분산과 새 명령을 누적한다.
2. 화물을 들었으면 정적/관측 장애물의 현재·후퇴 외곽을 검사하고, **자기 발행 low 자세로
   내려놓기→열기→팔 접기→15cm 명령 후퇴→지도 지형지물 둘러보기**를 한다.
   잡은 화물의 세계 좌표·접촉·측정 관절은 읽지 않는다. 열린 뒤 새로 보이는 대상만 다시 잡는다.
   내려놓기 위치 기억은 자기 low 집게 FK와 자기 명령으로 전파한 **몸 상대 시선 목표**뿐이며
   주행·파지 목표로 쓰지 않는다. 원래의 근거리 교사/ACT 경로를 대체하지 않는다.
3. 기존 `LookaroundLocalizer`의 벽·구역선·문 모델과 정보 증가 기반 시선 선택을 재사용한다.
   팬만으로 정보가 없으면 내려놓은 상태에서 몸을 돌린다. 기존 0.35rad/s 시간 가정 대신
   **자기 발행 명령으로 적분한 yaw**를 따라 회전하고 마지막 관측 뒤 불필요한 복귀 회전을 없앴다.
   수용은 기존 rank·다중 그룹·chi-square·정보 증가 검사를 모두 거친다.
   fix가 없거나 수용 후에도 예산이 부족하면 `carry_relocalization_unconfirmed`로 정지한다.
   3회 같은 자리 재확인 또는 총 12회 초과도 종료한다. 재확인만 반복하며 무기한 진행하지 않는다.
4. **회전 절약:** 운반은 운반 시작 방향을 유지하며 전후·옆걸음으로 웨이포인트를 따른다.
   목적지 최종 정렬만 별도로 한다. 접근 지도 경로도 몸 상대 목표 방향을 유지한다.
   최종 슬롯이 막히면 동일한 정적 구역의 다섯 후보를 다시 검사한다. 모두 막히면 재관측한다.
5. **주차:** `carry5_parking_v1`은 검출기가 지원하는 최대 거리 4m의 peer 원반을 사용한다.
   `0.26 + hypot(0.15,0.15) + 0.06 + 0.08×4 + 0.20 + 0.01 = 1.062m` 경로 여유다.
   옛 0.59m를 사용하지 않는다. 장면 배치용 경로·주차 좌표는 제어기에 전달하지 않는다.
6. **트랙:** 범위 오차와 자기 위치/yaw 오차로 2D 공분산을 만들고 Mahalanobis d²≤9.21로
   같은 종류를 일대일 연결한다. 동일 프레임의 두 물체를 하나로 병합하지 않는다.
   같은 자세 오차를 공유하는 연속 관측으로 공분산을 인위적으로 줄이지 않는다.
   수용된 자세 보정은 트랙 좌표에도 같은 강체 변환으로 반영한다.
   미관측 시간만으로 장애물을 지우지 않는다. 낮은 자세 불확실성, 비-held 상태, 화면 내부의
   전체 예상 영역, 색 물체/어두운 가림이 없는 바닥 무늬가 **3회·1초 이상** 확인되면 삭제한다.
   실제 시야에서 이 삭제 판정과 covariance의 보정 정확도는 미검증이다.
7. robot 후보에서 노란 화물 hue 대역을 제외하고, 주황만으로 로봇 판정을 내리지 않도록
   아래쪽 어두운 차체/바퀴 증거를 요구한다. 이는 미검증 RGB 형태 규칙이며 인식 성공 주장이 아니다.
   pickup 원반 제외는 고정 0.12m 대신 footprint+범위 오차+0.08m를 사용하되,
   **종류가 맞고 모호하지 않은 단 하나**만 제외한다. 다른 색·같은 색의 다른 화물은 유지한다.
8. 중간 내려놓기 횟수·`uninterrupted_carry=false`를 평가에 별도로 기록한다.
   운반 구간 보존과 의도적인 중간 내려놓기를 숨겨서 무중단 운반 성공으로 보고하지 않는다.
   localizer 예외 시 입력 전 자세·공분산도 복구한다. runner의 기존 0.1초 틱은 유지한다.

## 실제 v4 지도·발행 명령 재현

`python -m scripts.audit_solo_carry5 --raw <회수된93220>/raw --out <결과.json>`.
`diagnostic-plan-v4.json`의 8개와 실제 `CarryToZone`, A*, `duty_wheels`, `CommandPose`를 쓴다.
가짜 지도·계획기 스텁·물리 엔진은 쓰지 않는다. 접근은 계획의 nominal station까지 실제
경로 추종 명령을 적분한다(자세 관측이 아님). carry5는 첫 재확인에서 멈춘다.
마지막 열은 검토자식 **운반 시작점 예산=0 반사실**이며 실제 fix를 받았다는 뜻이 아니다.
수치 시각은 각 명령 재현 시작부터이며 실제 실행 SIM 성공 시간이 아니다.

| v4 시드 | 종류/구역 | v4 첫 종료 | carry5 첫 재확인 | fix 이후 명령 거리/회전 | 계획 뷰 | 운반 시작 예산0 반사실 |
|---|---|---|---|---|---|---|
| 93220 | cyan / A | 19.7s / unavailable | approach 14.3s | 1.308m / 0.0° | 3 | 12.4s / 3뷰 |
| 93221 | red / C | 9.3s / stale | carry 12.9s | 1.290m / 0.0° | 3 | 12.3s / 3뷰 |
| 93222 | green / C | 11.4s / stale | carry 12.9s | 1.280m / 0.0° | 3 | 12.4s / 3뷰 |
| 93223 | yellow / A | 19.7s / unavailable | approach 14.3s | 1.308m / 0.0° | 3 | 12.4s / 3뷰 |
| 93224 | cyan / A | 20.3s / unavailable | approach 15.6s | 1.287m / 0.0° | 3 | 12.4s / 1뷰 |
| 93225 | red / C | 9.3s / stale | carry 12.9s | 1.290m / 0.0° | 3 | 12.3s / 3뷰 |
| 93226 | green / C | 11.4s / stale | carry 12.9s | 1.280m / 0.0° | 3 | 12.4s / 3뷰 |
| 93227 | yellow / A | 19.7s / unavailable | approach 14.3s | 1.308m / 0.0° | 3 | 12.4s / 3뷰 |

carry5 **8/8**은 하드 가드가 열린 상태에서 재확인으로 분기하며 **8/8**에서 3개 관측 방향을
계획한다. 수용 RGB fix는 **0/8(새 관측 미실행)**이다. fix 미수용 분기는 모두 종료한다.
검토자의 원래 재현 스크립트는 지정 경로에 없어서 같은 방식의 독립 명령 재현을 작성했다.
v4 시작 즉시 종료 분류는 이번 4/8, 검토자 3/8로 차이가 있으며 바이트 동일 재현으로 부르지 않는다.
양쪽 모두 복구 없는 종료는 8/8이다. **물리 효과·전체 운반 완주·RGB fix 수용률 미검증.**

## 검증과 의존성

공용 모델 병합 전 관련 8개 파일 **142 passed** (`offline-tests-carry5.txt`).
병합 후 모델·carry5·carry4 **50 passed** (`offline-final-carry5.txt`),
마지막 소비 경로/runner 관련 3개 파일 **70 passed in 53.04s**
(`offline-integration-carry5.txt`). 서로 겹치는 시험 수를 합산하지 않는다.
실제 v4 8개 경로, 하드 가드 이전 분기, 지도 기반 시선, 무정보 영상 fix 거부,
held 상태 내려놓기 후 실제 관측 호출, 수용된 특징 잔차의 epoch 초기화,
슬롯 재선택·트랙 연결/삭제·단일 pickup 제외·기본 off 원본 바이트를 검사했다.
runner 시험만 가짜 backend를 사용하며 새 물리·렌더 검증과 구분한다.

공용 `drive_model_deadband_v1`은 **중복 구현하지 않았다**. origin fetch 뒤
`claude/drive-model-deadband`의 **01703ed2790dadad666e53d1b276b97f2b510bda**를 병합했고
carry5 계획에서 켰다(`carry5-dependency.json`). add/add 충돌에서 기존 v6 학생 계약과
pickup_site를 유지하고 공용 모델의 M1/M2 API를 통합했다. 구형 carry 프로필은 계속 off다.
한 로봇·틱마다 relay를 **한 번만** 적분해 지도 자세, 교사의 상대 기억·후퇴 거리,
lookback 원위치 기억이 같은 증분을 쓴다. 다른 고정 오차 계수를 겹쳐 적용하지 않는다.
재집기마다 lookback 인식을 새로 시작하고 grasp별 증거 파일명을 분리했다.

공용 모델은 확인된 감쇠 B=(T0−Tk)/omega0를 사용한다. 원인 미확인 추가 감쇠를
임의로 보정하지 않아 저장 원본 분석상 M1 과대가 약 10–15% 남는다(공용 모델 README).
따라서 데드밴드 반영을 완전 보정으로 부르지 않는다. 위 carry5 표는 이 모델 ON으로
다시 계산한 값이다. 물리·가림·접촉·RGB fix 수용률은 여전히 미검증이다.

새 계획 `diagnostic-plan-v5.json`: **93240–93247**, 4색×2. 로컬 등록부 4개와 기존 대기열
96개에서 충돌 0건(`carry5-seed-check.json`). 원격 미사용 여부는 접속 금지 때문에 미확인이다.
기존 대기열은 수정하지 않는다. 새 SHA 대기열은 **첫 1개→검토/승인→나머지 7개 직렬**이며
`approved/ready/runs_enabled`와 각 run의 `enabled/ready/approved`는 모두 false다.
원격 승인·시드 확인·비용/저장공간·첫30초·영상 점검은 실행 담당자의 미완료 조건이다.

## 참고 자료 — 확인한 출처와 적용 범위

- [Burgard, Fox, Thrun, Active Mobile Robot Localization, IJCAI 1997, pp.1346–1352](https://www.ijcai.org/Proceedings/97-2/Papers/080.pdf):
  공개 원문의 초록·§3.2에서 미래 belief entropy를 줄이는 행동/센서 방향 선택을 확인했다.
  여기서는 기존 Gaussian 정보 증가(log-det) 기반 지도 시선 계획을 재사용했다.
  논문의 sonar 전역 Markov localization을 구현했다거나 같은 성능을 냈다는 뜻은 아니다.
- [Stone Soup 1.7, Data association—clutter](https://stonesoup.readthedocs.io/en/v1.7/auto_tutorials/05_DataAssociation-Clutter.html):
  예측과 검출의 Mahalanobis 거리 및 missed-distance gate를 확인했다.
  여기서는 2D 가정 공분산 gate와 greedy 일대일 연결을 쓴다. JPDA나 최적 GNN 구현은 아니다.
- [Stone Soup 1.7, Initiators & Deleters](https://stonesoup.readthedocs.io/en/v1.7/auto_tutorials/09_Initiators_&_Deleters.html):
  track 생성/삭제를 별도 생명주기로 관리하고 불확실성이 큰 트랙을 삭제하는 예를 확인했다.
  우리 경로는 맹목적 시간 만료로 장애물을 없애지 않고 세 번의 확인 가능한 빈 시야를 요구한다.
  임계값은 개발 가정이며 실제 오검출/가림 데이터 보정은 남아 있다.
- 프로젝트 재사용: `sim/active_lookaround.py`, `sim/lookaround_localization.py`,
  `sim/grasp_act_solo_lookaround.py`, 자기 카메라 FK와 기존 색/윤곽 검출,
  `scripts/zone_teacher.py`의 A*. 정답은 별도 평가에만 사용한다.
