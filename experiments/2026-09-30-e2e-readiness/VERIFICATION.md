# 문서 감사 검증 기록

기준 코드: `a8094cc14e098a55483f53a3c49bf6a0b116043d`. 작성/검증일: 2026-09-30.

이번 산출물은 READINESS.md, 독립 작업 프롬프트9개, 이 검증 기록의 **Markdown11개**다. 기존 코드·설정·실험 기록을 변경하지 않았다. 아래 검사는 문서 구조/링크·계획 산술·현재 코드의 정적 제한을 검증한다. 새 실험·로봇 성공·provider/물리 결과가 아니다.

## 검증 방법

아래 Python은 표준 라이브러리만 쓰며 프로젝트 모듈을 import하지 않는다. MuJoCo/torch/모델/네트워크/서브프로세스를 시작하지 않는다. 문서 내 검사용 코드 블록을 제외하고 상대 링크를 검사한다. 저장소 루트에서 실행한다.

```python
from pathlib import Path
import ast
import hashlib
import json
import re
import unittest

ROOT = Path.cwd()
OUT = ROOT / 'experiments/2026-09-30-e2e-readiness'
REPORT = (OUT / 'READINESS.md').read_text()
PROMPTS = sorted((OUT / 'task_prompts').glob('P*.md'))


class ReadinessDocumentChecks(unittest.TestCase):
    def test_01_local_references_resolve(self):
        count = 0
        for file in sorted(OUT.rglob('*.md')):
            prose = re.sub(r'```.*?```', '', file.read_text(), flags=re.S)
            for target in re.findall(r'\]\(([^)]+)\)', prose):
                if '://' in target or target.startswith('#'):
                    continue
                count += 1
                self.assertTrue((file.parent / target.split('#')[0]).exists(),
                                (file.name, target))
        self.assertGreaterEqual(count, 140)

    def test_02_every_stage_has_all_six_fields(self):
        sections = re.split(r'(?m)^### S(\d{2})\.', REPORT)
        self.assertEqual(sections[1::2], [f'{i:02}' for i in range(1, 16)])
        for ident, content in zip(sections[1::2], sections[2::2]):
            for field in ('있는 것', '마지막 측정/조건', '미측정', '빠진 연결',
                          '최소 닫기 시험', '예상 SIM 비용'):
                self.assertIn(f'**{field}', content, (ident, field))
            self.assertRegex(content, r'\]\([^)]*(?:\.py|\.md|\.json|/pull/)')

    def test_03_self_contained_prompts(self):
        self.assertEqual(len(PROMPTS), 9)
        for file in PROMPTS:
            text = file.read_text()
            for phrase in ('AGENTS.md', 'CONTRIBUTING.md', 'worktree', '물리',
                           '렌더', '모델', '금지', '검사', 'SIM', '병합',
                           '--repo kcm0127-dotcom/ugrp', '참고 자료',
                           'Generated with Codex',
                           'Co-Authored-By: Codex <noreply@openai.com>'):
                self.assertIn(phrase, text, (file.name, phrase))

    def test_04_plan_arithmetic_and_scope(self):
        gates = [3*30 + 3*300 + 2*60, 5*180 + 3*300 + 3*60,
                 90*120 + 3*120, 12*900, 4*1800, 4*1800]
        self.assertEqual(sum(gates), 39450)
        self.assertEqual(round(sum(gates)/3600, 2), 10.96)
        self.assertEqual((24+72)*1800/3600, 48)
        for value in ('39,450', '10.96', '마일스톤을 완료 처리하지 않는다',
                      'teacher 재배치', 'TOP와 정답', '평가 전용'):
            self.assertIn(value, REPORT)

    def test_05_provider_allowlist_and_model_identity(self):
        config = json.loads((ROOT / 'configs/zone_study_integration/pose_providers.json').read_text())
        provider = config['providers']['vision_zero_tag_v2']
        self.assertEqual(provider['maps'], ['zone_wide_door_geometry_v2'])
        self.assertFalse(provider['uses_landmark_tags'])
        self.assertFalse(provider['research_result'])
        worker = json.loads((ROOT / 'configs/vision_loc_worker.json').read_text())
        self.assertEqual(worker['model']['sha256'],
                         '348539030fda962cc5ba64e21c956619bc4db9321a99cd3ae6746611a9939fd9')

    def test_06_cited_runtime_restrictions_exist(self):
        sources = {
            'harness/zone_own_executor.py': ['KIND_NOT_SUPPORTED_BY_M1_SKILL',
                                            "order['kind'] != 'cyan'"],
            'harness/zone_study_integration.py': ["roles = {'r1': 'end_neg', 'r2': 'end_pos'}",
                                                 'UNSUPPORTED_TEAM_ORDER'],
            'scripts/run_zone_study_integration.py': ['M2 dev supports a pair-only order',
                                                       "cargo[0]['item_id'] != team_orders[0]['order_id']"],
            'harness/vision_pose_source.py': ['self.loc.predict_to(now)',
                                             'self.loc._pf.last_scan_t = None'],
            'harness/zone_pair_executor.py': ['PAIR_PICKUP_OUTSIDE_M2_DOOR_ENVELOPE',
                                             'UNSUPPORTED_PAIR_MAP'],
        }
        for name, fragments in sources.items():
            text = (ROOT / name).read_text()
            ast.parse(text)
            for fragment in fragments:
                self.assertIn(fragment, text, (name, fragment))

    def test_07_final_environment_and_scenario_scope(self):
        door = ROOT / 'maps/zones/zone_wide_door_geometry_v2.json'
        self.assertEqual(hashlib.sha256(door.read_bytes()).hexdigest(),
                         '0a8f5fdc3b3ad01710971a9f5caf020eb76c7e90f3da5713e669d035b4e7ebaf')
        self.assertNotIn('landmarks', json.loads(door.read_text()))
        scenarios = sorted((ROOT / 'configs/zone_study_scenarios_v2').glob('*.json'))
        self.assertEqual(len(scenarios), 6)
        kinds = set()
        maps = set()
        for file in scenarios:
            value = json.loads(file.read_text())
            self.assertEqual(value['landmark_detail'], 'none')
            self.assertEqual(value['eval']['budget']['sim_seconds'], 1800)
            kinds.update(row['kind'] for row in value['orders'])
            maps.add(value['map_id'])
        self.assertEqual(len(maps), 3)
        self.assertTrue({'cyan', 'red', 'green', 'can', 'tile', 'long_beam', 'heavy_crate'} <= kinds)

    def test_08_markdown_only_small_artifacts(self):
        files = [file for file in OUT.rglob('*') if file.is_file()]
        self.assertEqual(len(files), 11)
        self.assertTrue(all(file.suffix == '.md' for file in files))
        self.assertLess(sum(file.stat().st_size for file in files), 5*1024*1024)
        self.assertTrue(all(file.stat().st_size <= 1024*1024 for file in files))


suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReadinessDocumentChecks)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 8 else 1)
```

추가 검사: `git diff --cached --check`, 변경 파일 목록/범위 확인. GitHub 이슈/PR 상태는 GitHub API로 읽고, 열린 개발 결과와 main 결과를 분리했다. 과거 실측 수치는 원 보고서와 코드 제한을 대조했으며 원본 코호트 전체 재집계는 하지 않았다.

## 결과

- **문서 검사8/8 통과**, Python3.12.13(기존 `.venv-sim-worker-mac` 인터프리터, 프로젝트/모델 모듈 import 없음), 0.023초. 시간은 검사 로그이며 성능 비교가 아니다.
- 상대 링크140개 누락0,15단계 각각6항목, 독립 프롬프트9개, 파일11개 모두 Markdown. 첫 연결 계획의 합계39,450 SIM초=10.96 SIM-h와 정식24+72회 추가48 SIM-h 산술 일치.
- 현재 provider allow-list/분할 모델 hash, cyan-only/M2 역할·pair-only 제한, 재측위의 posterior 보존, 최종 무표식 map hash와6시나리오 구성은 **JSON/소스 텍스트·AST 읽기만으로** 대조했다. 해당 소스가 실제로 실행되는지는 검사하지 않았다.
- `git diff --cached --check` 통과. staged 변경은 이 폴더의11개 Markdown 추가뿐이며 기존 코드·설정·실험 bytes 변경0.
- 검사기 준비 중 `unittest.main()` 자동 검색이0개를 실행한 결과는 통과로 세지 않고 explicit suite+8개 수 검사를 넣었다. 초기8개 검사에서는 P08의 모델 호출 금지·SIM 예산 표기가 다른 프롬프트보다 덜 명시적이라 문구를 보완했다. 최종8개가 모두 통과했다.

실행 명령(저장소 루트):

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PY'
from pathlib import Path
import re
p = Path('experiments/2026-09-30-e2e-readiness/VERIFICATION.md')
code = re.search(r'```python\n(.*?)\n```', p.read_text(), re.S).group(1)
exec(compile(code, str(p) + '::<document-checks>', 'exec'), {'__name__': '__main__'})
PY
git diff --cached --check
```

원격 push·draft PR은 이 기록을 담은 커밋 뒤에 수행한다. 이 커밋 자체가 원격 CI 통과를 주장하지 않는다. 최종 응답/PR에 실제 확인한 상태를 별도로 적는다.

## 실행하지 않은 검사와 이유

- 전체 pytest/회귀/CI: 문서만 변경한다. 작업 중 `claude/v6h1-acceptance-run` 물리 인수 시험의 살아 있는 공용 잠금이 확인돼 직접 pytest로 우회하지 않았다. 위 표준 라이브러리 검사는 파일/문서만 읽는다. 원격 CI 결과는 push 이후 별도로 표시한다.
- MuJoCo/물리/렌더/비전·LLM 호출: 사용자 금지 범위라0회다. fake-wire 저장소 테스트도 이번 문서 작업에서는 실행하지 않았다.
- 기존 raw 재생·모델 재로딩·TensorBoard 재변환/서버/브라우저: 새 실험 결과를 만든 작업이 아니며 수행하지 않았다. 대시보드 URL은 후속 확인용 안내다.
- 병합·기본 체크아웃 갱신·Drive: 사용자 요청에 따라 draft PR까지만 수행한다. UGRP는 Drive를 사용하지 않는다.
