# s3fix11 — Oracle x86 단계 묶음 (2026-10-10)

## 실행 전 등록

사용자 요청으로 새 물리·렌더·저장 제어 재생은 `host=oracle-x86`에서만 실행한다.
AMD EPYC x86_64, 64 logical CPU, 62GiB, Ubuntu24.04, MuJoCo3.12.0/OSMesa.
Mac은 편집·관련 pytest1–3파일·기록 변환만. ARM 신규 실행0, Mac 잠금 대기0.
서버 다른 작업과 합쳐 동시20개 이하, nice0, 각≤60SIM초/dev_light.
동일 비교는 이 호스트 안에서만 하며 ARM/Mac 시간·바이트 동등성을 주장하지 않는다.

새 bundle `zone-s3-x86-stage-probe-v156`, workflow7.49.0. main과 열린10PR 원격의
최대v155/7.48.0 확인 후 예약했다. v155 ARM 실행기·원본은 변경하지 않는다.

우선 기준12개: pair(r1/r2 정렬→hover→하강→닫기)6개 + cyan(r3 정렬→상승→운반)6개.
각 조건 i=0..5는 seed14201+i와 다음 자기 차체 기준 시작 오프셋(dx,dy,yaw)을 고정한다.
`(0,0,0),(.012,0,0),(-.012,0,0),(0,.012,0),(0,-.012,.04),(0,0,-.04)` (m,rad).
pair 두 로봇에 각자의 차체 기준으로, cyan은 r3에만 적용한다. 기존 scene-setup의
eval-only 장면 구성기에만 반영하고 제어기는 매번 새 자기RGB 전역PF로 시작한다.
이것은 저장 장면의 합성 주변 조건이며 정확 체크포인트 재개·독립 확증·E2E가 아니다.
시드를 골라 성공으로 바꾸지 않고 여섯 조건을 전부 보고한다.

v3 마운트는 host 렌더 바인딩, alignment entry는 발행한 inspect 유지 옵션on.
공통 heading 기본on, 집기/놓기/문 최종0.10m 옆걸음 허용, 공동 빔운반 예외 유지.
weld/topRGB/GT제어/시작dock prior 없음. 기존 3mm/0.035rad 판정 문턱은 변경하지 않는다.
PF `sensor_mixture_v1`은 미검증·기본off를 유지하며 입자 수를 늘리지 않는다.

## 판정과 다음 수정의 선택 규칙 (결과 열람 전)

raw 상태/명령/자기RGB/평가 전용 접촉으로 로봇별 hover·하강·닫기·접촉상승·운반,
오차/검출/회전반전, would_stop, 실제정지, wall/SIM을 판정한다. HOST_ERROR/미회수는 별도.
pair baseline의 알려진 회전진동은 시야 검출과 실제 이동을 분리해 확인한다.
후보는 PBVS의 완전 강체변환(집기점 lever arm 포함)과 측정된 합법 단일축 pulse만 사용한다.
새 pulse는 ≥0.10초·실물 최소35출력 계약을 유지하고 물리 보정 결과 없이 이득을 추정하지 않는다.
채택 조건: 동일6조건에서 정렬/닫기 도달 증가, 기존 성공의 실제 물리 실패 증가 없음,
원래 문턱 유지·GT입력0. 후보가 실패하면 같은 원인 반복 대신 기록하고 full smoke는 보류한다.
1시간 진전이 없으면 중단·보고한다. 후속 보정/후보 조건은 실행 전에 이 문서에 추가한다.

## 참고 자료

[Chaumette·Hutchinson 2006, PBVS/interaction matrix](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf):
목표 feature의 변화와 카메라 이동을 전체 좌표변환으로 연결한다. 집기점 오차를 차체 원점의
목표 경로 방향으로 취급하면 회전의 lever arm 항을 잃는다. 우리 단일축/유한 pulse 제약은
이 변환을 각 측정 primitive에 적용하고 자기RGB로 다시 관측하는 방식으로 유지한다.
[MuJoCo rendering](https://mujoco.readthedocs.io/en/stable/python.html#rendering): OSMesa 경로 사용.

## 결과

미실행. 실행 소스를 커밋·push한 뒤 묶음을 보내고 완료/실패 모두 추가한다.
