# 실행 기록

- 사전 등록24f2f6f7 → 구현/주석346db610 → 관련17시험 통과·push 후 개발 시작.
- 첫 실행은 s1042의863개 own 예측과 eligibility를 모두 저장한 뒤 출처 목록의
  `markerless_probe.py` 경로 오기로 receipt 작성에서 HOST_ERROR가 났다. RGB 추출 오류가 아니다.
  실제 모듈은 `experiments/2026-09-26-markerless-probe/markerless_probe.py`였다.
- 경로만 교정하고 모든 hash 경로를 RGB 전에 확인하도록 했다. 기존 predict 함수 AST 및
  모든 다른 source bytes가 원346db610과 같음을 검사해 **저장된 예측을 재사용**한다.
  원 prediction/source hash·metadata 복구 source를 구별한다. s1042 재계산/원본 삭제0,
  나머지 개발 s1043만 처음 계산한다. 실패1회와 그 출력/관리 session 정상 정리를 보존한다.
- 첫 합성 LK 시험에서35px 반복무늬의20px 이동이 역방향 correspondence로 alias되는 것을
  확인했다. 알고리즘을 조정하지 않고 이 자료는 behind-camera 거부 반례로 유지하고,
 5px 이동의 정상 삼각측량 시험도 병기했다. 실제 녹화 결과를 본 임계값 조정이 아니다.

새 s1050/1051 주석12개는 RGB만 보고 기록했고 parallax 계산 전에 구현 커밋에 봉인했다.
총8건4,361 eligible frame이며 무하중21자세만 비교한다. annotation-check 원본 그림은 raw에 보존.
