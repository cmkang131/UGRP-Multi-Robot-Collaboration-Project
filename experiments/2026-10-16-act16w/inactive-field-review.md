# dof_length 차단 — 고정 소스의 정적 조사

GPU/물리/렌더0, 후보 미구현·런타임 미검증.
warp1이 기록한 설치 pin `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148`의
공식 소스를 HTTPS로 받아 `_src` Python64개를 검색했다. 실제 VM 설치 파일과
이번에 다시 해시 대조한 것은 아니다. [다운로드·파일 해시·참조 목록](inactive-field-source-audit.json).

- [types.py:1728](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/types.py#L1728): dof_length는 world-batch가 아닌 nv 배열이다.
- 명시적 실행 참조는 [sleep.py:313](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/sleep.py#L313)의 속도 norm 가중치와 같은 파일의 wake/update_awake 경로에만 있다. 나머지는 types 정의다.
- [forward.py:2189](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/forward.py#L2189)는 SLEEP on이면서 ISLAND off가 아닐 때 wake/update를 호출한다. io.py의 sleep 동기화도 별도 SLEEP 조건으로 감싼다.

따라서 **모든 world에서 SLEEP bit가 명시적으로 OFF인 프로필에 한해** dof_length만
미사용 필드로 취급하는 입장 검사 후보를 검토할 수 있다. 첫 모델의1D 필드를 그대로
남기고, 이 필드만 world 차이 거부 검사에서 제외하는 방식이다. 질량·관성·기하·실제
파생 역학 필드의 차이는 기존처럼 batch 가능한 필드로 복원하거나 거부해야 한다.
SLEEP을 켠 실행에서는 이 예외를 절대 적용하지 않는다. 지원되지 않는 explicit
sleep enum을 다른 enum으로 근사하는 제안도 아니다.

이는 정적 검색에 따른 **추론/후보 근거**이며 실행 동등성의 증명이 아니다. 적용 전
설치 소스 SHA와 SLEEP flag를 실제 확인하고, 고정 입력의 N16 qpos/qvel/contacts 및
첫 자기 RGB를 on/off로 검증해야 한다. 그 뒤 독립40회 교사 관문은 별도로 필요하다.
이 후보로 속도가 개선된다는 근거는 없고, full-scene physics 비용은 별도 문제다.
