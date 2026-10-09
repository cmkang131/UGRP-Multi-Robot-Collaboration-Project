# 결과 전 구현 점검

사전 등록 커밋 `5b2aba3f`. 최초 outcome 채점/본 replay 이전에 확인한 사항이다.

- 여섯 지도 모두 마지막 online snapshot과 frontend-grid의 frame/resolution/cells는 동일하다.
  전체 dict는 이후 odometry/공분산/입자/계수 갱신 때문에 다르다. 최초 생성자 smoke는 과도한
  dict 동일성 검사로 중단했다. 입력으로 사용하지 않는 동적 상태를 제외하고 지도 3필드의
  일치만 검사하며, 실제 변환은 명시한 마지막 online grid에서 한다. 지도 선택·관문 변경 없음.
- 생성자 연결 중 provider_factory 중복 인자와 function-binding의 metadata 누락을 수정했다.
  RGB/명령 재생 전 생성자 오류이며 새 지도/PF 상수 조정은 없다. 수정 후 100,000개 시작 입자가
  모두 자기 지도 observed-free에 놓이고 route=[]/slot=None, 기존 camera_v3 변환 유지 확인.
- S2의 exact-map admission은 기존 그대로이다. 새 모듈 내부의 private binding에서만 자기 map을
  전달하고, 카메라/운동 calibration은 기존 exact hash로 검증한 동일 값을 이전한다.
  생성자 호환용 legacy map_id는 시작 위치를 제공하지 않으며 외부 산출물은 ownmaps2a/own frame.
- 점유 셀을 가로 run으로 합친 obstacle rectangle은 생성자 호환용 무손실 2D 표현이다.
  미관측 height는 0 placeholder이며 sensor는 자기 grid EDT만 사용한다. 3D guard/경로/운반
  기능에는 이 지도를 사용하지 못하게 step/drive/_control을 명시적으로 차단한다.
- 확인된 floor 경계가 없어 S2 MapFeatures의 regions는 비어 있고, B 부분 관측은 observed_regions에
  원래 범위/출처와 함께 남긴다. 이미 본 부분의 바깥을 GT 구역으로 채우지 않는다.
- 평가 프레임 변환은 mapping-run 첫 eval trajectory chassis pose의 강체 SE(2)뿐이다.
  평가-only oracle의 관측지원 거리 0.4m는 사용자 제시 20–40cm 오차 규모를 사용하며,
  coverage는 0.2/0.4m 모두 표시한다. 이 설정은 첫 본 replay 이전에 고정했다.

## 입력 목록 정정 (비교 outcome 개봉 전)

자기 branch의 `RememberedGoal.lose()`를 추가 추적하여 `snapshot.json.landmarks`를 발견했다.
이는 기존 grid/remembered-goal 파일 밖에 저장된 실제 own 관측이며 누락하면 지도 교체 검증이
불필요하게 약한 입력을 사용한다. 첫 baseline 재생 중 발견해 소유 세션만 중단했다. 비교 후보는
아직 시작하지 않았고 전체 baseline/후보 outcome은 채점하지 않았다. 원래 시도 raw는 보존한다.
`registration-v2.json`은 관문·pair 배정 그대로, snapshot 파일의 해시/존재 여부만 추가한다.
엄격한 실행 전 등록으로 소급하지 않고 DEV 사전 관문 + 입력 목록 정정으로 명시한다.

| 자기 지도 | 실제 저장 floor edges | observed doors | snapshot |
|---|---:|---:|---|
| 49001 | 6360 | 0 | 있음 |
| 49002 | 6452 | 0 | 있음 |
| 49003 | 0 | 0 | 없음, 만들어 채우지 않음 |
| 49004 | 0 | 0 | 없음, 만들어 채우지 않음 |
| 49005 | 6163 | 1 | 있음 |
| 49006 | 6364 | 0 | 있음 |

이 행들은 지도 저장 형식 확인이며 위치추정 성능 결과가 아니다. partial_extent bounding box는
여전히 경계로 쓰지 않는다. 관측된 partial edge를 원래 프레임·hue·normal·출처 그대로 받으며
기존 S2 ML correspondence의 후보로만 사용한다(같은 관측을 독립 likelihood로 중복 곱하지 않음).

입력 정정 뒤 시험 13개 PASS. snapshot partial edge/door 보존, GT/peer/future 정보 거부,
273개 합성 pose에서 기존 floor+door likelihood와 tiled 구현의 2e-12 상대오차 일치를 확인했다.
6천 edge × 10만 입자의 모든 후보를 한 번에 저장하지 않도록 128-particle tile로 계산한다.
후보 제거·재표본화·sigma·likelihood tempering·중복 관측 가중치 조절은 없다.
실제 7개 입력 hash/geometry 일치, 49001의 6360 edge가 실제 측정 closure에 연결됨을 확인했다.

## 재생 인프라 수정 (상수/입력/관문 변경 없음)

`78103a8c` 첫 baseline 5846프레임은 pose 7필드가 저장 기록과 정확히 일치했다(최대 차이0).
첫 own 생성자는 등록된 exact-speedup이 HighPoseSource.__init__을 감싼 상태에서 private binding을
시도해 실패했다(`cannot bind an undeclared frozen dependency`). r2 세션을 중단하고 원본·실패를
보존했다. `inspect.unwrap`으로 원 생성자만 private-bind한 뒤 동일 ExpectedMemo를 다시 부착한다.
실제 등록 speedups+실제 고정 calibration을 사용하는 생성자 회귀를 추가했다. 보정/튜닝 없음.

## 제공된 소스의 환경 차이 (비교 채점 전 확인)

7개 pair 모두 mapping `zone_wide_two_doors_final_v3`와 S2 `zone_wide_door_geometry_v3`의
`scene.xml` 분리벽이 다르다. `wall_divider_1`은 mapping에서 y=-1.1625, half-length=.9625,
S2에서 y=-1.675, half-length=1.475이다. 즉 아래쪽 1.025m 구간은 mapping에서 실제로 열린 곳이다.
바닥 regions는 동일하다. 자기 지도에서 이 벽이 없는 것을 전부 미관측 실패로 해석하면 안 된다.
벽/영역 해시와 원본은 r2의 `source-environment-audit.json`에 기록했다. 비교는 요청한 기록 그대로
계속하되 **동일 물리 경기장 통제 실험으로 표현하지 않는다**. 운반 통합 전 동일 장면 비교가 남는다.

## 최종 봉인과 CI 선택 의존성

`b9a76350`의 r3 14조건/82,326 frame-instance가 모두 완료되었다. 기준 7조건의 pose 7필드는
최대 수치 차이0 및 직렬화 해시 동일, 모든 예측 출력 해시 일치, 최종 HOST_ERROR 0이다.
재생이 끝나고 세션 종료를 확인한 뒤에만 아래 시험/평가 보조 스크립트를 추가했다.

원격 CI 37890979958은 6/8 shard의 실제 speedup 생성자 시험에서 MuJoCo 미설치로 실패했다.
기존 S2 시험과 [pytest 공식 선택 의존성 처리](https://docs.pytest.org/en/stable/how-to/skipping.html#skipping-on-a-missing-import-dependency)를 확인해
해당 시험 안에서만 `importorskip('mujoco')`를 사용한다. 설치된 Mac 환경에서는 그대로 실제
생성자를 검사하고, 미설치 환경에서도 다른 13개 시험은 실행한다. 시뮬레이터 world/step을
생성하는 시험이 아니며, 필터·센서·관문·등록 입력은 변경하지 않았다.

추가 평가 스크립트는 봉인 결과만 읽는다. 공통 벽 coverage, 상한 없는 벽 거리, 원본 GT
궤적의 grid support, 실제 후보/기준 feature 수, 자기 벽+관측지원 GT 벽의 true-pose 점수를
평가 전용으로 남긴다. 마지막 두 항목을 새 수렴/운반 성공으로 세지 않는다.

## 평가·표시 시도의 한계

추가 mode-score v1은 report 전달 시각으로 pose를 골라 센서 시각과 어긋났다. 주 평가는
처음부터 t_est를 사용하므로 영향이 없다. v1 JSON은 로컬에 보존하고 결론에는 쓰지 않는다.
정확히 같은 t_est가 없는 v2는 7개 모두 unavailable로 남긴다. mode jump 사이를 보간해
임의의 pose를 만들지 않는다. 벽 coverage/GT true-pose 혼합 점수/실제 feature 수 진단은 별개다.

TensorBoard 첫 helper 호출은 `main(argv)`를 지원하지 않는 기존 CLI를 함수처럼 호출해 실패했다.
이벤트는 생성되지 않았고 `tensorboard-inputs/`를 보존했다. 기존 `scripts/export_offline_audit.py`
CLI를 subprocess로 호출하는 방식으로 수정해 새 derived 디렉터리에서 14/14 변환·검증했다.
표준 변환기·기존 snapshot은 변경하지 않았다. 공용 HParams의 첫 experiment schema 선택 때문에
새 custom 열이 표시되지 않는 제한은 delivery/README에 남기며 Time Series로 결과를 보여준다.
