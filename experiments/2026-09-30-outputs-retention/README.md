# outputs 보존 3차 — 참조를 추적한 재분류, 실제 삭제 없음

**원본 증거를 보존하면서 남은 삭제 후보는 캐시 0.567879 GiB, 13,794개 파일이다.**
2차 후보 23.74 GiB 중 1,008,759개 파일을 보존으로 돌렸다. D1 프레임 솎기, D2 퇴역 실행 bulk,
D5 JSON 사본은 이번 삭제 목록에 없다. 모델 입력·학습 자료·보고 수치의 원본은 유지한다.
남은 후보는 모두 `status-video/remotion/node_modules/`의 재설치 가능한 패키지 파일이다.
폴더 전체가 아니라 manifest에 고정한 파일만 후보이며, 참조로 보호한 패키지 파일도 남긴다.

**DO NOT EXECUTE.** 이 작업은 읽기 전용 재검토안이다. 코디네이터의 재검토·사용자 승인을
거친 별도 실행 전까지 삭제하지 않는다. 1·2차 manifest를 실행하거나 세 배치를 합산하지 않는다.
`/Users/changmin/projects/ugrp/outputs/`에서 삭제·수정·이동·압축한 파일은 **0개**다.
조사 DB와 테스트용 가짜 outputs는 `/private/tmp/`에만 만들었다.

## 바뀐 판정과 용량

| 구분 | 파일 수 | 할당 GiB | 판정 |
|---|---:|---:|---|
| 3차 삭제 후보 | 13,794 | **0.567879** | 기존 D3 재설치 가능한 캐시 중 참조 보호에 걸리지 않은 파일 |
| 리뷰어 제외 합집합 | 724,107 | 18.286400 | 전부 보존; 파일 수·바이트·정렬 경로 해시 일치 |
| 고정 보존 목록 | 1,775,068 | 61.681007 | 원래 보존 파일 + 2차 후보에서 되돌린 파일 |
| 별도 사용자 결정 질문 | 86,859 | 4.258045 | 아래 세 연구의 이미지. 현재 전부 보존 |

리뷰어 제외와 질문 목록은 보존 목록의 부분집합이며 서로 더하지 않는다.
GiB는 `st_blocks × 512 / 2^30`이다. 재고는 **78.247349 GiB**, 같은 목록 적용 후 예상값은
**77.679470 GiB**다. 동시 작업 중 읽은 재고이므로 원자적 스냅샷이 아니며 APFS 실제 확보
공간을 보장하지 않는다. 실제 확보량이나 원격 백업 완료를 뜻하지 않는다.

## 내용·참조 그래프

1. [독립 리뷰](REVIEW_RETENTION_astra.md)의 [제외 목록](reviewer-exclusions.json)을 전부 적용했다.
   폴더 전체 제외와 `fnmatchcase` 패턴을 그대로 해석했다. 경로 합집합 SHA-256은
   `59b4eb61c1f8c8c299913e009fe4730d28aec9734cca3ea7e70b79f8d62986a3`이다.
2. outputs의 JSON/JSONL/CSV/TSV/log/txt 및 gzip 파일 **201,647개**를 읽었다.
   두 로컬 checkout의 experiments와 HEAD/main/열린 PR의 관련 Git blob까지 합쳐
   **212,184개 출처**를 기록했다. 조사한 ref와 정확한 SHA는 manifest에 고정했다.
   모든 키·문자열의 이미지 경로와 SHA-256, 인라인 이미지, CSV 셀, JSONL·worker log를 추적했다.
   `image_hashes`의 키, learned approach/grasp 경로, 압축된 `frames.jsonl.gz`도 포함한다.
   분리된 run/case/robot/frame 필드는 실제 이미지 경로로 연결했다.
3. 보고 문서와 분석기의 입력을 추적해 **25,302개 폴더 보호 연결**을 만들었다.
   `eval_*`/`analyze_*`와 리뷰에 언급된 분석기, 파일 읽기·glob, 보고된 실행군 전체를 포함한다.
   glob은 실제 대응 폴더를 보호한다. 동적 입력을 정적으로 확정하지 못한 D1/D2 자료도 보존한다.
   보존 조사기 자체의 코드·설명은 과학 분석기로 보지 않지만, 그 JSON/CSV 참조는 동일하게 읽었다.
4. 모호한 상대 경로나 동일 해시는 가능한 모든 대응 파일을 보존한다.
   파싱 오류 **71건**의 출처·오류 종류와 불확실한 생산자 자료군도 보존한다.
   오류에는 의도적으로 깨진 테스트 fixture와 동시 기록 중인 운영 자료가 포함된다.
   미참조라는 이유만으로 원래 후보 밖의 파일을 새로 추가하지 않았다.
5. 원래 고정 분할 1,788,862개 파일의 전체 해시를 검증하고 삭제 후보를 축소했다.
   새 파일·최근 파일·실행 중 파일은 무조건 보존하며 해시 동결을 강제하지 않는다.
   JSON 사본도 기록의 내용/경로/해시 참조에 해당하면 보존하므로 D5 후보는 0개다.

출처·참조·보호 사유는 [그래프 요약](round3-graph-summary.json),
[분석기 입력 추적](round3-script-inputs.json), `round3-graph-{sources,refs,folders,protected}*.json*`에 있다.
각 catalog는 정확한 행과 해시를 묶은 zlib+base64 **JSON 메타데이터**이며 원본 영상이 아니다.
참조 catalog에는 실제 재고와 대응된 경로/해시만 공개하며 요청 본문·인라인 이미지·비밀값을 복사하지 않는다.

## 코디네이터가 사용자에게 확인할 선택 항목

아래는 연구 원본 영상을 포기할 의사가 있는지 묻는 목록이다. **실행 목록이 아니며 현재 전부 KEEP**다.
JSON/JSONL/CSV 결과·모델·영상 파일은 유지한다. 선택 후에도 다른 연구의 모델 입력 의존성을
다시 확인하고 정확한 별도 manifest를 만들고 검토해야 한다. 학습·추론 입력 E1/E2와 체크포인트는
질문 대상으로 넣지 않았다. 정확한 파일 수·바이트·경로 및 내용 지문은
[선택 질문 기록](round3-optional-decisions.json)에 있다.

| 연구 | 이미지 GiB | 삭제 시 잃는 능력 |
|---|---:|---|
| 9/25 TOP RGB 작업 결과 판정 v1/v2 | **3.958** | 전후·시계열 픽셀로 delivered/미확정, false-delivered 수치와 판정 시점 재검증 |
| 9/25 상자 4색 검출 평가 | **0.135** | RGB·정답 segmentation으로 오검출·색별 재현율·위치 오차 재채점 |
| 9/25 AprilTag 자기 카메라 위치 추정 평가 | **0.165** | 태그 재검출부터 위치 오차·자세별 태그 가시율까지 원본 영상으로 재검증 |
| 합계 | **4.258** | 결과 JSON만으로 위 픽셀 검증을 대체할 수 없음 |

## 현재 기록과 검증

- [manifest.json](manifest.json)은 `round3-delete/`·`round3-keep/`와 모든 그래프 근거의 해시를 묶는다.
  [manifest.csv](manifest.csv)와 [inventory.csv](inventory.csv)는 같은 폴더별 가산 합계다.
  [summary.json](summary.json)은 현재 3차 수치다.
- 각 배치는 파일명·크기·mtime_ns·전체 파일 SHA-256의 정렬 기록에 묶인다.
  [dry-run.json](dry-run.json)은 실제 원본을 읽은 검사 결과이고,
  [round3-consistency.json](round3-consistency.json)은 이전 분할 유지·새 후보 0·제외/보호 교집합 0을 검사한다.
  이번 dry-run은 후보 13,794개·보존 1,775,068개의 해시 검증을 통과했다.
  종료 시 다른 작업의 `physics` 잠금(PID 21249)이 있어 실행은 차단 상태였으며 잠금을 건드리지 않았다.
- 독립 임시 디렉터리의 테스트 **80건 통과**. 기존 삭제 실행기 60건과 참조 추출·리뷰 패턴·glob 경계·
  불완전 분류 시 manifest 발행 차단 등 20건이다. 원본 outputs에는 실행 테스트를 하지 않았다.
  [JUnit](unit-tests.xml)과 [verification.json](verification.json)에 명령·소스 지문·검증 범위를 남긴다.
- `round2-*`, `folder-details/`, `thinning*`, `json-reconstruction*`, `plan-consistency.json`,
  `remaining-largest.csv` 등 기존 보조 파일은 **과거 1·2차 기록**이다. 현재 후보나 검증 결과로 사용하지 않는다.
  2차 전체 상태는 Git `70f2f09c46bdc1e265af70fb44111f5906324dff`에도 보존되어 있다.
- 새 연구 실험 결과가 없어 TensorBoard 재변환·서버 조작·Drive 작업을 하지 않았다.
  물리·모델 호출·모델 배포·실제 삭제·병합은 이 검증 범위에 없다.

읽기 전용 재검사:

```sh
python3 scripts/outputs_prune.py experiments/2026-09-30-outputs-retention/manifest.json
python3 experiments/2026-09-30-outputs-retention/audit/round3_check.py
```

새 재고로 재조사하려면 `audit/round3_graph.py`의 `inventory → references → classify → emit` 순서로
별도 임시 scratch를 사용한다. 이전 manifest나 raw를 덮어쓰지 않는 새 검토 배치로 남겨야 한다.
