# 18차 체크포인트 — 재생 판정의 소스 범위와 자산 identity

**새 조건부 P2는 보존된 optional Gemini replay의 물리 소스 검사 누락 1건이다.** 정상 recorder가 기록한 `harness/real_geometry.py`를 replay의 prefix filter가 건너뛴다. 현재 HIGH pair의 성공·실패 원인을 새로 찾은 결과는 아니다.

| 결과 | 판정과 근거 | 활용 |
|---|---|---|
| [Replay source 검사](replay.md) | 실제 writer/replay 판정의 10개 합성 대조와 별도 형상 소비자 검증. 기록된 geometry 파일이 달라도 source predicate 통과 | 알려진 물리 의존성을 source closure에 포함하는 수정 기준. 실제 다른 물리 궤적이 전체 valid를 통과했다는 주장은 하지 않음 |
| [1mm·명령 소비·정지의 범위](boundaries.md#replay) | 초기/최종 cargo XYZ, 마지막 평가 표본의 robot XYZ, 선택된 명령 소비가 기준. 현재 stop 기록 대조는 정상 | `valid=True`를 전체 자세·접촉·궤적·task 성공으로 승계하지 않음 |
| [Reference 자산 연결](boundaries.md#reference-assets) | 실제 준비→preflight→consumer prefix에서 catalog 13개와 backend 입력 11개 연결. 다섯 변경/누락 유형 차단 | 이 좁은 identity 경계는 확인됐으며 새 결함 0개. Scene 생성·모델 추론·full admission은 미실행 |
| [비교에 필요한 서로 다른 증거](research.md) | 자산 identity, applied execution, 관측/행동 시퀀스, exposure/claim scope의 실제 필드 구분 | 같은 파일 hash만으로 실행 동일성이나 학습 미노출을 인증하지 않음 |

검토 pin은 직접 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`다. 공식 09:02 UTC 재조회에서 main·#363 `66ff0978`·#371 `a009112f`는 직전 pin과 같았다. PR의 base snapshot을 live main으로 쓰지 않았다. 현재 active 문제의 [15차 attachment](../round15/attachment.md), [16차 camera 실패](../round16/posture.md), [#371 runtime](../round8/runtime.md)과 이번 optional 경로는 구별한다.

[독립 검증](validation.md)에 재실행·source-only 검토의 경계를 모았다. 원고 13개와 1–17차 본문은 보존했다. 구현 변경·실제 physics/render/model/학습·raw 실험 재생 없이 [19차 독립 재도전과 후속 검토](backlog.md)를 계속한다.
