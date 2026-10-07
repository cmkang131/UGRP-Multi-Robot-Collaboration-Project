# 실행 기록

- 사전 등록 `e240df27`, 구현 `7428987b`; 관련14시험 통과 후 구현 커밋.
- 조건 감사: s1045/46/47/50 모든30,512프레임 join. 조건별 표는 `results/conditions.csv/json`.
- 첫 개발 영상 계산은 예측 봉인/오차 채점 이전 `IndexError`로 중단했다.
  OpenCV5 `LSD.detect()[0]`는 N×4, 원문은 OpenCV4 N×1×4를 가정한다.
  원문 `__detect_lines`의 `lines[:,0]`도 같은 가정이다.
  어댑터에서 양쪽을 N×4로 normalize한 뒤 원문과 동일한 LSD0/30px 결과를
  subclass의 선분 입력에 전달한다. 원문 파일·가설·점수·seed·관문은 변경하지 않는다.
  이 호환 변경은 prereg 후 데이터 품질 결과를 보기 전에 수행한 실행 오류 수정이다.
  빈 실패 디렉터리 `outputs/online-camera-pitch-v1/online_vp_v1/s1042` 보존,
  재시도는 새 `outputs/online-camera-pitch-v1-complete/`에 저장한다.
  같은 원인으로 다시 실행이 막히면 반복 수정 없이 중단한다.
