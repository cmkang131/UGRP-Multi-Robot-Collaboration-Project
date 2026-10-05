# R21 — 그림자 인식/teacher 계약의 독립 범위 검토

**최종 원고 범위 QA: PASS. 판정 단위와 입력 예외를 분리하는 해석에 동의한다.** 새 구현 결함·실제 실패 재현·이슈 완료를 주장하지 않는다. source pin은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`다.

공식 이슈/PR 내용은 담당자가 저장한 `shadow-teacher-official-sources.json`에서 읽었다. 이 QA가 API를 독립 재조회한 것은 아니다. 선정 12개 소스의 세 pin, 총 36개 Git object hash를 독립 대조해 모두 일치했다. 추가로 main의 AGENTS, outcome v1/v3 tracker, teacher gate를 읽었다. `shadow-teacher-independent-source-check.json` (Mac 전달본 증거). UGRP module·테스트·물리·렌더·모델을 실행하거나 raw/결과/이미지/가중치를 열지 않았다.

| 확인 지점 | 직접 읽은 계약과 해석 |
|---|---|
| #220의 shadow | 공식 제목·본문의 의미는 자기 손목 영상의 그림자/가림 오류다. evaluator의 `LIGHTING`도 조명 스트레스를 정의한다. shadow-mode 실행기 검토로 바꾸지 않는다. |
| S1 대 A3 | `compute_gates`의 S1은 stress `record='view'`에서 unknown/정답을 제외하고 confidence 기준 이상 오류를 세어 0과 비교한다. A3는 밝은 부분 가림의 `record='view'`, `status='confirmed'` 오답을 보고하며 `report_only`에 들어간다. A3는 해당 10개 pass/fail gate 중 하나가 아니다. |
| 두 지표의 표본 단위 | `score_views`는 tick 관측을 `outcome.track`에 모아 view×judgment 결과를 낸다. 따라서 S1도 단일 raw frame/tick 오류수가 아니다. helper만 보면 S1은 status를 검사하지 않지만, 정상 tracker의 unconfirmed 출력은 unknown/confidence 0이어서 제외된다. A3와 S1의 이름 차이만으로 ‘단일 영상 대 다중 영상’이라고 해석하지 않는다. |
| 최종 수용 기준 | #220은 사전 등록 기준과 표식 없는 최종 렌더 재평가를 요구한다. 옛 S1=0을 최종 통합의 모든 지표 기준으로 재명명하거나 A3에 새 zero-error 기준을 소급해 붙이지 않는다. 이번 선정 source에서 새 최종 acceptance를 찾지 못했다는 범위를 넘어, 저장소 어디에도 계약이 없다고 증명한 것은 아니다. |
| teacher 예외 | #225 및 `run_zone_teacher_fix`는 시연·학습 표적/실현 가능성 지원으로 명시한다. `zone_teacher_gate`는 setup config 기반 시작 허용 여부를 판단하며 그 gate 통과가 학생 성공이 아니다. 교사의 GT/IK/접촉 권한을 학생의 독립 정책 입력으로 이전하지 않는다. |
| TOP green 조건 | `zone_color_boxes.TOP_ZONE_HSV`의 green 하한 S100과 cargo v1/v2의 해당 profile 호출을 읽었다. 이것은 소스 조건의 지속성이지 공개 seed22 S98 영상이나 실패 세 건을 재현한 것이 아니다. S100 하나만으로 이미지 전체의 검출·제어 결과가 결정된다고 주장하지 않는다. |
| 현재 소비 범위 | `tile_own_vision.inspect`는 `image_information` 실패 시 unknown 관련 결과를 반환하고 통과 시 tile 전용 판단으로 진행한다. helper 재사용은 v3.1의 모든 judgment/성능 계약을 승계하지 않는다. 명시 import 검색은 확인된 연결의 범위이며 동적 연결까지 포함한 전역 부재 증명이 아니다. |

main AGENTS의 기본 관측 행에는 공용 TOP을 포함하는 문맥도 남아 있다. 따라서 교사 예외를 설명할 때 AGENTS의 학생 경계 전체가 #220의 자기 wrist/TOP 평가전용 문구와 동일하다고 쓰지 않는다. 이 두 이슈와 현재 과제의 더 좁은 입력 계약을 명시적으로 유지하는 것이 맞다. 문서 권한을 새로 변경하거나 학생 TOP 사용을 권고한 검토가 아니다.

독립 검토의 결론은 **확인된 caller/metric 의미에 대한 수용**이다. 공개 수치의 검산, 물리적 일반화, 실제 현재 HIGH 중단 원인, 과거 모든 실행의 provenance는 검증하지 않았다.

최종 cross-read: `shadow-teacher-scope.md` SHA-256 `694a0484911e13a8de10873f1c84095ba37f2697abd39e0edb11ceba8a83840a`. 앞서 권고한 S1/A3의 view 단위, tracker의 unknown 출력, 명시 import 검색의 한계가 반영됐다. teacher 시작 TOP→detector→색 profile과 teacher 결과 scope도 실제 source에서 확인했다. #363 OpenCV 기본 provider와 #371 VisionWorkerClient 경로를 좁게 대조했으며 둘을 같은 caller로 합치지 않은 설명을 수용한다. 독립 공개 수치 재채점이나 실행 검증은 아니다.

## 배포 wrapper만 바뀐 후속 확인

`shadow-teacher-source-check.py` SHA `7ef1d18bc22534412e4797b5347524b1cf0b1ee07690b917ad7caf04bbcb514b`의 필수 `--repo/--output`, 새 파일 전용 `open('x')`, 기존 evidence 경로 보호를 읽고 독립 임시 출력에 한 번 실행했다. 종료 0, 기존 golden JSON SHA `808ab59402635331412359d888d79681b4d591058814cc6f25497d8439f66b4d`와 byte-identical이었다. 같은 출력 경로 재호출과 필수 인자 누락은 각각 exit 2이고 기존 파일/golden은 불변이다. `--output -`의 JSON stdout·요약 stderr 분리는 source로만 확인했다. `shadow-teacher-independent-source-check.json` (Mac 전달본 증거).

의존성은 Python 3 표준 라이브러리, git 실행 파일, 세 고정 SHA의 Git object가 들어 있는 UGRP checkout이다. UGRP module이나 실험을 실행하는 script가 아니며 원고/기존 evidence의 의미·바이트도 바뀌지 않았다. 이 후속은 source/AST 도구의 호출·출력 wrapper 검사이고 학생 정책이나 과거 실험의 새 검증은 아니다.
