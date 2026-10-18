# r14 단독 case27 3회 결과 (2026-10-18 10:03Z)

**2/3 PASS — 안정 조건(3/3) 미충족.** align refresh 수정은 이번 라운드에서 발동하지 않았다.

|회차|결과|align|relook|align_refresh_begin|summary sha256|
|---|---|---|---|---|---|
|rep1|PASS sim 24.1|2.7 s|0|**0**|(remote-sha 참조)|
|rep2|PASS sim 24.0|2.6 s|0|**0**|(remote-sha 참조)|
|rep3|**FAIL sim 25.5**|7.8 s|3|**0**|(remote-sha 참조)|

## 관찰

- 실패 rep3는 기존 실패 signature(align 7.8 s·relook 3)와 동일하며, `align_refresh_begin` 이벤트가 **한 번도 없었다**.
- 즉 r14의 align-phase refresh 훅 조건(reobserver idle·최종 cmd hold·goal_set_log 존재·`remembered_blockers` 비어있지 않음) 중 `remembered_blockers`가 빈 dict를 반환했을 가능성이 높다. `remembered_blockers`는 `world['visibility'][rid]['observations']`에서 stale cargo를 찾는데, 실패 시점(17.6 s 이후)에는 해당 관측이 이미 memory에서 만료되어 비어 있을 수 있다.
- next(재개 시): align hook에서는 observations 대신 `truth['objects']`(stale memory 포함)에서 goal 근처 cargo를 targets로 구성해 begin하도록 수정하고, 3회 반복 재검증. (Lead 지시로 beam 라운드는 여기서 중단.)

## 보존 원본

- `r14-single27-rep1..3` (gcp6 디스크), summary/first30·SHA는 이 디렉토리 `runs/r14-single27-rep*/`.
- stack: teacher `f1cf1926` / adapter `d4398363` / root `3bc6708c` / cases r14diag `e6236377`; prereg `1181b4391`.
