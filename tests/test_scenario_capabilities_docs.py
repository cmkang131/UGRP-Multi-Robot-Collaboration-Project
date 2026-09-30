"""P09 review regressions: CI instructions and the P02/T02 scope boundary."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
P09 = ROOT / "experiments/2026-09-30-scenario-capabilities"
PROMPT = ROOT / "experiments/2026-09-30-e2e-readiness/task_prompts/P09_scenario_capabilities.md"


@pytest.mark.parametrize("path", [
    P09 / "CI_INCIDENT.md", P09 / "VERIFICATION.md", P09 / "README.md",
    P09 / "TASKS.md", PROMPT,
], ids=lambda path: path.name)
def test_local_execution_limit_does_not_disable_normal_ci(path):
    """B3: every entry point must keep CI enabled, including the handoff prompt."""
    text = path.read_text()
    assert "정상 GitHub CI는 허용" in text
    assert "취소하지 않는다" in text
    assert "건너뛰지 않는다" in text
    # Historical cancellation/skip evidence stays; these future directives do not.
    assert "후속 기록 커밋은 `[skip ci]`로" not in text
    assert "후속 문서 커밋에는 `[skip ci]`를 사용한다" not in text
    assert "CI 재실행·병합도 하지 않는다" not in text


def test_t02_is_a_separate_extension_with_its_own_owner_and_budget():
    """B4: six scenarios must not silently expand #307's cyan+beam contract."""
    tasks = (P09 / "TASKS.md").read_text()
    t02 = tasks.split("## T02 —", 1)[1].split("## T03 —", 1)[0]
    assert "P02 다음의 별도 확장 과제" in t02
    assert "담당 미정" in t02
    assert "cyan 1개 + 봉 1개" in t02
    assert "#307의 완료 조건에 소급 추가하지 않는다" in t02
    assert "2×900=1,800" in t02
    assert "4조건×1800=7,200" in t02
    assert "별도 시험" in t02
    assert "P01/P02 소유" not in tasks
    for text in (tasks, (P09 / "README.md").read_text()):
        assert "T02(P02 소유)" not in text
        assert "(P02 소유)" not in text
