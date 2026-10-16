# 작업·검증 기록

2026-09-28 · `codex/masterpi-public-specs`

## 범위와 저장소

- 작업 경로: `/Users/changmin/projects/ugrp-wt/codex-masterpi-specs`.
- 시작 HEAD: `d5bd208e45331a73f1f71dd9b3e129c26c5eaac6`. 시작 시 작업 트리 깨끗함. 로컬 `origin/main` 및 GitHub 연결 도구로 확인한 main과 같았다.
- 로컬·기본 체크아웃·원격 main의 AGENTS 지침, README, current_status, CONTRIBUTING을 확인했다. 기본 체크아웃은 읽기만 했고 갱신하지 않았다.
- `origin`은 이전 URL `https://github.com/kcm0127-dotcom/ugrp.git`. 연결 도구로 요청 대상 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`의 실제 저장소와 main을 확인했다. 공용 Git 설정을 바꾸지 않았다.
- `git fetch origin`은 외부 공용 메타데이터 `.../ugrp/.git/worktrees/codex-masterpi-specs/FETCH_HEAD` 쓰기가 `Operation not permitted`로 거부됐다. `gh pr list`도 API 네트워크 연결에 실패했다. 대신 GitHub 연결 도구로 열린 PR 11개와 관련 PR head를 읽었다.
- 확인한 #249 head `961271a44ad34cf17e94f36217589af7cde2fa2a`, #251 head `6c91f2ded2181d5022780af411d749826533d9b2`, #248 head `29fedc3e0638d680da32d4753d645925a20edbef`는 해당 로컬 원격 추적 ref와 일치했다. 이후 변경까지 추적한 기록은 아니다.
- 중복 구현 방지를 위한 #249 조사 범위 코멘트 게시를 시도했으나 GitHub 도구가 `MCP tool call requires approval, but approval policy is never`로 거부했다. 게시되지 않았다. 관련 PR 코드 변경은 하지 않았다.

## 조사와 보존

- 공식 제품/치수도·문서·SDK와 사본·판매처·커뮤니티·연구 자료를 읽었다. 출처와 실패 URL은 `sources.md`, 값과 근거는 `public_specs.json`에 기록했다.
- 기존 로컬 참조 이미지 6개는 읽기·해시만 확인했다. 새 이미지 복제/커밋 없음. 원격 현재 이미지 바이트와 보존본의 동일성까지 확인한 것은 아니다.
- 보정 NPZ는 임시 경로에서 `allow_pickle=False`로 숫자만 읽었다. 카메라 보정 실행이나 물리/시뮬레이션/모델 호출은 하지 않았다.
- 다른 작업의 코드·프로세스·raw·공용 설정은 변경하지 않았다. Google Drive 사용 없음, 새 번들 ID 없음, 태그/부착 고정 도입 없음.

## 검증

- JSON 파싱과 템플릿 키 포함 검사 PASS: 정적32/32, 추가3항목으로 총35개. 초음파spec·카메라intrinsics·dynamics·servo·gripper·drive의 기존 비메타 키도 유지했다.
- 147개 값 객체의 필수 필드·출처 ID/URL·null 상태 검사 PASS. 출처44개. 보정 완료/배포 허용 필드는 설정하지 않았다.
- 원본 픽셀×인쇄 축척 계산22건 PASS(환산 사본 포함). 참조 이미지6개 전체 SHA-256·크기 일치. 새 이미지0개.
- 로컬 Markdown 참조10개 검사 PASS(게시용 PR 본문 링크를 원격 브랜치 URL로 바꾸기 전).
- 사용자 지정 테스트 명령:

```sh
OMP_NUM_THREADS=2 ../../ugrp/.venv-sim/bin/python -m pytest -q -p no:cacheprovider --basetemp=./.pytest_tmp tests/test_real_geometry.py
```

결과: **7 passed in 0.13s**, 종료코드0. 성공 줄 확인 후 `.pytest_tmp` 부재를 확인했다. 대상은 math 기반 FK·투영 함수의 단위 테스트로 로봇·물리·모델을 호출하지 않는다. 사용자 지정 직접 pytest 경로를 사용했고 다른 worktree/공용 잠금 파일은 변경하지 않았다. 테스트 성공은 실물 치수·카메라 보정·PHYSICAL 검증이 아니다.

## 저장·게시

로컬 결과 파일 작성 완료. `git diff --check` 통과. 변경은 이 worktree의 조사 폴더와 실험 인덱스뿐이다.

녹색 테스트 결과를 확인한 다음 사용자 지정 `git add --sparse -A`를 실행했으나 종료코드128로 실패했다.

```text
fatal: Unable to create '/Users/changmin/projects/ugrp/.git/worktrees/codex-masterpi-specs/index.lock': Operation not permitted
```

Git 메타데이터가 쓰기 허용 경로 밖에 있고, 현재 실행 환경은 승인 요청도 허용하지 않는다. GitHub 쓰기 도구 역시 위 승인 정책으로 차단됐다. 제한을 우회하거나 공용 메타데이터를 옮기지 않았다.

| 단계 | 상태 |
|---|---|
| 로컬 저장·JSON 검산·단위 테스트 | 완료 |
| staging | 실패: index.lock 쓰기 제한 |
| 커밋 | 생성 안 됨, 시작 HEAD 유지 |
| push | 미실행, 원격 백업 아님 |
| draft PR | 미생성; `PR_DRAFT.md`에 참고 자료 포함 본문 준비 |
| PR #249 조율 코멘트 | 도구가 거부, 미게시 |
| CI | 실행/검증 안 됨 |
| 병합·기본 체크아웃 갱신 | 미실행 |

쓰기 가능한 정상 Git 환경에서 이어갈 때 사용할 커밋 메시지:

```text
docs: MasterPi 공개 치수와 센서 사양 근거 정리

공식 도면·SDK·제품표의 값과 상충·미확인 항목을 보존하고
sim2real 템플릿 키에 출처와 신뢰도를 연결한다.

Co-Authored-By: Codex <noreply@openai.com>
```

이후 파일이나 관련 코드가 바뀌면 해당 상태를 다시 검증한 뒤 커밋한다. PR은 draft로 생성하고 병합하지 않는다. 새 번들 등록이 없어 ID는 예약하지 않았다.
