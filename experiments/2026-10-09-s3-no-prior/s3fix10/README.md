# s3fix10: Oracle 단계 probe (실행 전 등록)

2026-10-10 사용자 결정으로 Mac 물리·렌더·저장 재생은 중단한다. 이전 s3fix9 큐는 입력0/12·물리0 상태로 종료됐으며 대기 원본을 보존했다. Mac에서는 편집·커밋·관련 pytest만 한다. Oracle `oracle-a1`, ARM 8코어/24GB, 공용 MuJoCo3.12.0·OSMesa에서 커밋된 archive를 실행하고 원본을 회수한다. `~/stock-bot`·crontab은 접근·수정하지 않는다.

## 이번 묶음

v154를 보존하고 새 번들v155/workflow7.48.0으로 세 개를 병렬 실행한다. 각 ≤60 SIM초, wall상한30분, dev_light, heading기본on·공동파지 빔 운반만 heading예외, v3 호스트 마운트·weld off·자기RGB/명령/허용정적지도 조건은 그대로다.

1. pair-B: 실제 `align_start`, 카메라 자세 보존off. r1/r2 정렬→hover→하강→닫기.
2. pair-N: 같은 Oracle 장면·seed·실제 `align_start`, `preserve_issued_look_v1`만on. 같은 단계 판정.
3. cyan-carry: 기존 cyan 합성 접근 종료 위치에서 실제 RGB 정렬→hover→하강→닫기→기존 상승·운반 제어를60초까지 실행. 기존 probe의 닫기 후1초 종료만 이 새 번들에서 해제한다. 파지·상승·운반은 eval_only 접촉/높이/이동으로 각각 판정하며 발행 close를 성공으로 간주하지 않는다.

원본v152의560초 주변 정답은 **장면 재구성 owner에만** 쓴다. `scene-setup.json`은 원본 로그 SHA와 선택한 행을 보존한 작은 추출물이다. 컨트롤러는 새 전역 자기RGB 필터이며 초기 위치 정답·새 Gaussian prior를 받지 않는다. r3는 v152에서 정렬에 도달하지 못했으므로 기존v153과 같은 합성 stage entrance임을 표시한다. 정확한 checkpoint resume나 임무 성공을 주장하지 않는다.

세 실행은 같은 호스트에서만 비교한다. OSMesa/ARM/MuJoCo 버전 차이 때문에 Mac 영상·물리·궤적과 바이트 동일성을 요구하거나 승계하지 않는다. 보수 가드는 would_stop으로 기록하고 실제 낙하/기울기/집게 이탈/GO 실패/실행 오류만 정지한다. 원본 host의 실제 물리 정지는 HOST_ERROR와 구분해 기록한다. ENOSPC는 HOST_ERROR다. 임계값·seed·카메라 보정은 결과 뒤 변경하지 않는다.

새 입자 제안은 이 물리 묶음에서off다. s3fix9의 관측에 맞는 후보 선택 구현·선택 기준·참고 자료는 보존하되 100/500/새100 비교는 후순위다. 아직 새 비교 결과가 없으므로 채택하지 않는다. 먼저 raw를 보고 정렬·상승·운반 실패를 한 묶음으로 수정한다. 1시간 넘게 진전이 없으면 멈추고 남은 항목을 보고한다. Mac agent_lock 대기는 하지 않는다.

## 참고 자료와 기존 표준 경로

- [관측 제안 사전 등록·Mixture MCL/SRL 원문](../s3fix9/README.md#참고-자료)
- 기존 공통 `Scene`·v3 카메라 바인딩·실제 motor port 경로를 유지한다. 입력/기록 경로만 서버에 맞춰 분리한다.
- [MuJoCo Python headless rendering](https://mujoco.readthedocs.io/en/stable/python.html#rendering): 플랫폼별 OpenGL context 경로를 명시하고 실제 환경을 기록한다. Oracle 실행은 사용자 지정 OSMesa다.

실행 전 관련3파일의26개 통과, Oracle 환경 fixture의 우선순위 모의를 고친1개 재실행 통과: 총27개 확인. 실제 모터 stub 경로·Mac 실행 거절·archive SHA·닫기 후 상승/운반 상태 진행을 검증했다. 물리·렌더·저장 재생0.

상승 전 source 점검에서 S3 host는 낙하/기울기를 감시하지만 S2의0.3초 양손가락 접촉 이탈 가드가 없음을 확인했다. 새 r3 probe에만 기존 S2 `StopGuard`를 그대로 연결한다(높이0.06m·이탈0.3초·바닥0.005m·기울기10도, 수정 없음). GT는 별도 host의 abort만 결정하며 위치/행동 보정에 반환하지 않는다. pair와 기존v153/v154 기본 경로는 유지한다.
