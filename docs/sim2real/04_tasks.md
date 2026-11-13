# 04 병렬 과제 목록과 결과 양식

[안내](README.md) · [이슈 초안](tasks/ISSUES_DRAFT.md)

**13개 과제 모두 병렬 준비 가능**하다. 담당 칸은 비워 둔다. 의존은 전체 카드 완료 순서가 아니라 특정 산출물을 실제 로봇에 연결할 때 필요한 조건이다. 보정 과제는 기존 안전한 벤치 도구로 독립 측정할 수 있으며 T06 구현 완료를 기다릴 필요가 없다. 같은 장치의 구동 시간만 조율한다.

| 과제 | 한 줄 목적 | 필요한 것 | 산출물 | 물리 통합 의존 여부 | 담당 |
|---|---|---|---|---|---|
| [T01 환경·색](tasks/T01_environment.md) | 실물 색 분리 확인 | 벽·상자·자기 카메라 사진 | HSV 설정·마스크 평가 | 독립. T02에서 전처리가 바뀌면 재평가 | |
| [T02 카메라](tasks/T02_camera.md) | 시야·왜곡·장착 보정 | 자기 카메라·offline 보드·자 | K/D·장착 측정·검증 오차 | 정적 촬영 독립 | |
| [T03 바퀴 펄스](tasks/T03_wheel_pulses.md) | 이동량·불감대 측정 | 안전 벤치 구동·자·각도기 | 방향별 펄스 표 | 독립 벤치 가능, 연속 제어는 T06 중첩 정책 | |
| [T04 서보·집게](tasks/T04_servos.md) | 안전 범위·각도·폭 측정 | 기구 확인·각도기·캘리퍼스 | 관절별 표·허용 범위 | 독립 벤치 가능 | |
| [T05 팬·기울기](tasks/T05_pan_tilt.md) | 명령과 카메라 시선 대응 | 영상·서보 명령·측정 기준 | 환산 표·잔차 | 구동은 T04 안전 범위, 영상각 적합은 T02 보정값 | |
| [T06 명령 계약](tasks/T06_command_contract.md) | 10 Hz 어댑터·STOP 확인 | 시뮬 포트·가짜 transport·Pi | 계약·타임라인 | 모의 독립, 실물 서보는 T04 범위 | |
| [T07 기록기](tasks/T07_recorder.md) | 입력·명령·실패 증거 보존 | 저장 영상·기록기 | trace 감사·재분석 | 모의 독립, 실물 통합은 T06 이벤트 의미 | |
| [T08 색 추종 접근](tasks/T08_approach.md) | 접근만 분리 검증 | hybrid 접근 코드·상자 | 접근 오차·실패 원장 | 실물은 T01/02/03/06/07, 가동 팬 사용 시 T05 | |
| [T09 ACT 집기·들기](tasks/T09_act_pick.md) | 전처리·추론·파지 검증 | 모델·RGB·명령 이력 | 추론 지연·단계 성적 | 실물은 T01/02/04/06/07. T08 대신 안전한 수동 배치 가능 | |
| [T10 고정 놓기](tasks/T10_release.md) | 87행 재생 위험 확인 | 고정 시퀀스·초기 자세 | 재생 비교·놓기 성적 | 실물은 T04/06/07, T09 대신 안전 지지 초기화 가능 | |
| [T11 지도 없는 이동](tasks/T11_navigation.md) | 문·색 구역 이동 검증 | 초록 벽·구역·자기 RGB | 문/도착 성적 | 실물은 T01/02/03/06/07, 가동 팬 사용 시 T05 | |
| [T12 Pair 1비트](tasks/T12_pair_signal.md) | 허용 통신 채널 검증 | 두 endpoint·로컬 망 | 신호·단절 기록 | 통신만 독립, 구동 연결은 T06/07 | |
| [T13 SysID 되먹이기](tasks/T13_sysid.md) | 실측을 새 시뮬 버전으로 연결 | 기존 fitter·측정 형식 | 변수 대응·적합·holdout | 스키마 독립, 채택은 해당 실측 과제 결과만 필요 | |

각 카드의 수치 기준과 근거를 읽고 결과를 판정한다. 새 수치는 **초안 제안·실물 미검증·담당자 합의 필요**이며 합의 전에는 `draft`/`blocked` 상태다. 초안 기준을 만족해도 안전 인증·연구 일반화·다른 과제 완료가 아니다.

<a id="result-template"></a>
## PR 결과 template

각 카드의 `experiments/sim2real-<YYYYMMDD>-Txx-<run>/`는 저장소 루트 기준 **향후 생성할 상대경로 양식**이다. 현재 존재하는 결과 링크가 아니다. 코드 변경·실험·PR 게시 권한은 해당 후속 작업에서 별도로 따른다. 여기서는 문서 초안만 만든다.

각 결과 폴더에 `README.md`, `summary.json`, 카드별 측정 CSV/JSON, `manifest.json`을 둔다. 기존 측정 JSON/JSONL 스키마는 복사해 문서에 재정의하지 말고 [실측 템플릿](../../configs/real_measurements_template.json)과 [보정 자산](../../calibration/masterpi/README.md)을 사용한다. 아래 공통 summary는 기존 로봇 API가 아니라 **결과 sidecar 제안 양식**이다.

`README.md` 양식:

```markdown
# Txx 측정 결과
- 상태: draft / blocked / measured / accepted
- 검증 범위: mock / offline / sim / real (서로 합산하지 않음)
- 로봇 익명 ID, 날짜, 코드 SHA, 장면/카메라/명령/모델 해시:
- 재현 명령과 환경 버전:
- 기준: 프로젝트 계약 / 기존 문서 / 초안 제안
- 기준 근거와 담당자 합의 기록: 실기 사양·분포·문헌의 상대경로
- 계획 N, 시도 N, 측정 N, 통과 n/N, 미실행·실패·제외 사유:
- 관문별 누적 통과·거부 수, 측정 커버리지:
- raw 상대경로·sha256·접근/회수 상태:
- 안전 확인, 비상정지 결과, 관측 입력 감사:
- 실패 범주·막은 물체·최소 틈(미관측/미측정은 명시):
- 한계, 확인 안 됨, 다음 행동:
```

`summary.json` 양식(측정하지 않은 수치는 0이 아니라 `null`):

```json
{
  "task": "Txx",
  "status": "draft",
  "scope": "unverified",
  "source_sha": null,
  "robot_id": null,
  "planned": null,
  "attempted": null,
  "measured": null,
  "passed": null,
  "failed": null,
  "not_executed": null,
  "excluded": [],
  "coverage": null,
  "criterion_status": "draft_unvalidated_pending_agreement",
  "criterion_evidence": [],
  "agreement_record": null,
  "metrics": {},
  "funnel": [],
  "failures": [],
  "input_audit": {"forbidden_reads": null},
  "raw_manifest": "manifest.json"
}
```

`manifest.json` 양식:

```json
{
  "files": [
    {"path": "outputs/real_traces/<run>/events.jsonl", "sha256": null,
     "availability": "unverified", "purpose": "issued_commands"}
  ]
}
```

실제 PR에서는 placeholder를 실제 상대경로·해시로 채운다. raw가 공유되지 않았으면 `local_only` 등으로 명시한다. 공개 가능한 소형 요약만 PR에 넣고 큰 영상·로그는 기존 [증거 보존 규칙](../../CONTRIBUTING.md)에 따라 별도 보존한다. 평가용 외부 측정·성공 판정은 학생 입력 파일과 분리한다. `HOST_ERROR`, `cap_end`, 안전 중단, 미실행을 성공 분모에서 몰래 빼지 말고 전체 계획과 함께 별도 집계한다.
