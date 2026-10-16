# 최신 스택 기준과 제출 전 점검 (2026-10-17)

사용자: “이런 것들, 최신으로 업데이트 좀 제대로 해봐. 왜 자꾸 까먹는 거야”.

[흐름 감사표](flows.md)를 먼저 작성했다. 기준은 [current_stack.json](../../configs/current_stack.json) 38항목이며, `current`는 최신 결정의 요구값, `verification.source_artifact`/`notes`는 코드에서 확인한 범위다. 실제 적용값이 없는 경우는 **확인 안 됨**이다. main에 없는 열린 PR 모듈도 출처 SHA를 고정했고 적용 완료로 취급하지 않았다. 코드/설정·회수 요약을 본 감사와 실행·관문·학습·학생 성공은 별개다.

## 실행

표준 라이브러리만 사용한다. VM·시뮬레이터·렌더·모델·브라우저·네트워크를 호출하지 않으며 입력은 수정하지 않는다.

```sh
python3 scripts/check_current_stack.py /absolute/queue.json \
  --flow release --output /absolute/new-stack-check.json

# 같은 실행의 summary/manifest와 XML을 함께 검사한다.
python3 scripts/check_current_stack.py /absolute/summary.json /absolute/scene.xml \
  --flow release --output /absolute/new-runtime-stack-check.json
```

입력 JSON에 `flow`가 있으면 CLI를 생략할 수 있다. 서로 다른 JSON은 **각각** 완전하게 검사한다. 여러 파일의 빈 필드를 서로 메워주지 않는다. XML은 명령에 주어진 모든 JSON에 추가 증거로 적용하므로 같은 장면의 JSON만 같이 넣는다. XML만 넣으면 옵션 부분 검사이며 `partial_only`/종료1, 대기열 승인 불가다. 기존 출력 파일을 덮어쓰지 않는다.

종료0은 모든 적용 항목이 최신이거나 승인된 이탈/과거 재생으로 명시됐다는 뜻이다. `current_compliant=true`는 이탈·재생이 전혀 없을 때만 나온다. 누락/불일치/불완전한 승인/잘못된 JSON/모순된 flow는 종료1이다. 표에는 최신 외의 행을 모두 출력하고, 결과 JSON의 `rows`에는 최신 행도 남긴다.

## JSON 계약

`flow`: `teacher_gate`, `record`, `train`, `act_eval`, `beam_pair`, `release`, `self_map`, `e2e_llm`, `replay` 중 하나. `runs`/`episodes`/`worlds`/`results`/`attempts`가 있으면 비어 있지 않은 레코드 배열이어야 하며 모든 하위 기록을 검사한다. 상위 공통 선언과 하위 실제값을 **모두** 비교하므로, 한 세계의 옛 값을 상위 최신 선언으로 가릴 수 없다. 섞인 흐름은 루트에 flow를 강요하지 말고 각 하위 기록에 적는다.

`stack_values`는 정규화한 항목 id→실제값을 기록하는 새 공통 필드다. 점검기가 요구값을 자동으로 채워주지 않는다. 실제 실행기에서 읽은 값과 근거 manifest를 기록해야 한다. 기존 필드의 대체 경로는 각 기준 항목의 `verification.paths`에 있다. 여러 경로가 동시에 있으면 **전부** 맞아야 한다. `_required`처럼 요구사항만 적은 필드는 실제 측정값으로 읽지 않는다.

예를 들어 release의 일부 값은 다음 모양이다(완전한 제출 큐가 아니다).

```json
{
  "flow": "release",
  "stack_check": "/absolute/new-stack-check.json",
  "rejection_table": "/absolute/existing-funnel.json",
  "stack_values": {
    "physics_backend": "mjwarp_batch_v1",
    "contact_profile": "warp_native_contact_v1",
    "noslip_iterations": 0,
    "scene_profile": "walls_floor_contrast_v5_indigo110_s80",
    "localization_path": "texture_self_map_lk",
    "rbpf": "off",
    "held_world_reads": 0,
    "wall_cap": null,
    "gcp_host": "ugrp-act-l4-gcp3",
    "gcp_project": "ugrp-sim-c-1016",
    "gcp_account": "changmin5781@gmail.com"
  }
}
```

`texture_self_map_lk`는 이 기준표의 정규화 id다. 실제 경로는 `harness/e2e_rgb_vo.py:ground_pair` + 자기 명령 및 mapbuild 계열이며, 통합 모듈·관문 완료는 확인 안 됨이다. `rbpf=off`는 mapbuild6 판정 대기 상태다. RBPF/MASt3R 비교는 명시적 비교 이탈로 남긴다. 학습(`train`)에서는 물리 실행을 가정하지 않고 `dataset_provenance`에서 물리·접촉·장면 출처를 읽는다. 학습 호스트와 데이터 생성 호스트가 다르면 자료 출처와 학습 호스트를 각각 보존한다.

GCP 호스트·프로젝트·계정은 개별 허용 목록과 **조합**을 검사한다. gcp1은 허용 목록에 없고 gcp6만 별도 계정이다. 호스트 허용은 다른 작업자의 VM 사용 권한이 아니다. 실제 ownership·임대·budget-stop·idle20·실행 상한 없음은 운영 담당자가 장치 증거로 확인한다.

XML은 명시된 `option`의 noslip/cone/integrator/impratio와 equality weld를 읽는다. 누락 옵션은 기본값으로 추정하지 않고 미확인 처리한다. include는 자동으로 열지 않으며 standalone XML이 아니면 미확인이다. 질감 이름/색만 보고 정확한 장면 버전·카메라 입력·실행 백엔드를 추정하지 않는다. 선택적으로 `<custom><text name="scene_profile" data="..."/></custom>` 선언은 읽을 수 있지만 기존 장면을 고치지는 않는다. XML이 manifest와 충돌하면 차단한다.

## 이탈과 재생

의도적인 비교 또는 아직 통합되지 않은 항목은 다음처럼 **항목별** 이유와 이미 받은 사용자/조정자 승인 출처가 있어야 예외로 통과한다. `*`, 모르는 id, 중복 id, 빈 이유/출처, authority가 없는 선언은 거부한다. 점검기는 승인 출처 문자열의 진위를 인증하지 않는다. 조정자가 실제 승인 원문과 범위를 확인한다.

```json
{
  "stack_deviations": [{
    "id": "physics_backend",
    "reason": "MJWarp 학습 ACT의 CPU 확인 비교; primary와 합산하지 않음",
    "approval": {
      "authority": "user",
      "evidence": "AGENTS.md:45 @c8dc1e6545124ed69a996618bd11df684d233969: MJWarp 학습 ACT는 CPU E2E에서도 확인"
    }
  }]
}
```

이 예시는 CPU **백엔드** 비교만 승인한다. 옛 noslip10·장면까지 자동 승인하지 않는다. 각 이탈은 별도 항목/근거가 필요하다. 미측정 항목까지 이탈로 통과시키려면 미측정이라는 이유와 그 제한을 승인한 근거를 명시한다.

`replay_of`는 비어 있지 않은 원래 실행/manifest 경로다. 과거 재생에서는 원래 스택을 그대로 유지하고 최신 기준 불일치를 `replay_exception`으로 표시한다. `flow=replay`만 적고 원본 출처를 빼면 차단한다. 혼합 큐의 하위 replay는 그 하위 기록에만 적용되며 다른 새 실행을 면제하지 않는다. 새 실험을 원본 재생처럼 선언해서는 안 되며, 조정자가 원래 SHA/manifest를 확인한다.

## 조정자 승인과 결과 보존

큐를 최종 저장한 뒤 점검하고, 큐의 `stack_check`에 결과 파일 경로를 연결한다. 큐·기준표를 나중에 고쳤으면 새 결과를 만든다. 조정자는 `ok`, `admission`, 이탈 승인 원문, 결과의 `inputs[].sha256`/`stack.sha256`가 제출 큐/현재 기준표와 같은지 확인한다. 파일이 없거나 SHA가 다르면 승인하지 않는다. 기존 `rejection_table` 실재 파일 관문도 별도로 유지한다. 이 PR은 다른 작업자의 제출기를 수정하지 않는다.

[flows.json](flows.json)은 감사 칸별 상태·근거 id, [evidence.json](evidence.json)은 고정 SHA·파일 해시·줄 발췌다. 같은 워크트리에서 출처 발췌를 재확인하는 명령:

```sh
git show <evidence.json의 sha>:<path> | nl -ba
python3 -m pytest -q tests/test_current_stack.py
```

외부 참고 문헌을 새로 도입하지 않았다. 사용자 결정·로컬 소스·기존 회수 manifest가 근거다. 자동 비교 통과는 실제 물리/학생/위치 추정 성공의 근거가 아니다. VM/SSH/GUI/Mac sim/render/모델 호출0, 다른 작업 worktree·실행 변경0. 병합은 조정자가 한다.

## 확인한 결과

3라운드 안에서 최종 비물리 시험 **3 passed**. 38항목×10흐름 중 옛8·최신66·모름190·해당없음116칸이다. 고정 소스32파일의 전체 SHA와 발췌 줄, 입력 snapshot2개가 일치했다.

- `warp8-queue-check.json`: 기존 혼합 큐에 하위 flow가 없어 차단했다. beam/release를 임의로 같은 flow로 승인하지 않았다.
- `act16w-gate-check.json`: 최신3·미확인22로 차단했다. 회수된 교사40/40 자체를 부정하는 결과가 아니라 최신 스택의 실제값 기록이 부족하다는 판정이다.

[검증 기록](validation.json), [짧은 결과 요약](summary.json). `artifact-hashes.json`에는 이 작업 산출물과 코드/기준표의 SHA를 남긴다.
