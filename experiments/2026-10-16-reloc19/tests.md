# 비물리 검증

Mac 기존 `.venv-sim-worker-mac`에서:

```
python -m pytest -q tests/test_destination_visual_acquire.py tests/test_reloc18_innovation.py
```

R1 22 pass, 도착→획득 handoff 추가 후24 pass, R2 벽 제외·정보량 시점/복구 검사27 pass, R3 팬 탐색·복귀·발행 명령으로만 움직이는 RGB 기억·닫힌 집게 metric 관문 검사30 pass.
행동이 달라진 후보마다 gcp2 CPU 물리 진단을 별도로 실행한다. Mac 물리·렌더·GUI는 실행하지 않았다.
정적 검사는 시뮬레이션 성공·ACT 학생·학습·실물 성공의 근거가 아니다.

추가 관련 검사의 전체 실행은39 pass(그중17개는 기존 운반 결과/종료 감사); 최종 새 제어 검사 수30과 섞지 않는다.
신규 검사 파일은 `scripts/run_ci_tests.py`의 offline 목록에 포함했다. 원격 CI 상태는 PR에서 별도 확인하며 로컬 pass를 CI pass로 부르지 않는다.

물리 R3 소스는 `e042139b0930ee7b31eae08a917ff501ee01075f`로 고정했다. 이후 `destination_direction_preserve_v1` 기본 off 후보는 저장 원장의 실제 반례와 획득 단계 통합 검사까지 추가해 **33 pass**. 같은 실제 후보 함수로 R2 원장210/210건의 방향 왜곡 거부를 재생해 기존 관문 통과를 확인했다. **후속 후보 물리0회**이며 R3 결과를 이 후보의 성공 근거로 쓰지 않는다.

R3의 새 RGB 장애물이 기존 검색 목표를 막은 실제 원장을 추가했다. `destination_search_replan_v1` 기본 off는 막힌 경로를 기록하고 폐기하여 다음 유한 후보를 다시 고른다. 기존 충돌 관문을 완화하지 않는다. 두 토글의 실제 단계 검사 포함 최종 **35 passed in 1.32s** (`tests/test_destination_visual_acquire.py tests/test_reloc18_innovation.py`, Mac 비물리). 검색 재계획 후보도 물리 0회다.
