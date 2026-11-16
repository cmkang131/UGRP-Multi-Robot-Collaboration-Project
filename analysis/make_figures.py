#!/usr/bin/env python3
"""Paper figures from the main-experiment analysis output (cells.csv + tests.json of analyze_main.py).

  make_figures.py --name NAME [--arm ARM] [--mode zero|drop|one] [--backend auto|svg|matplotlib] [--note TEXT] [--out DIR]

Reads out/NAME/{cells.csv,tests.json}; writes out/NAME/figures/ (or --out): five figures + figures.json (the plotted numbers).
  a  structure means of C and the primary SP (scene bootstrap 95% interval, scene dots)
  b  shortfall (100 - C) split by representative cause (stacked, from `primary`, not from the multi-label tags)
  c  plan failure vs physical failure (C x S cell counts, reference-plan baseline beside the structures)
  d  distribution of the message count M per run (allowance 2R and the per-robot cap marked)
  e  against the reference-plan baseline (same scenes only)
Scoring is not re-implemented: cells are parsed back to typed cells and handed to analyze_main.Book / bootstrap_ci, with the
mode, interim flag, seed, bootstrap count and primary SP read from tests.json meta. Standard library only; matplotlib is used
when importable (`--backend auto`), otherwise (or with `--backend svg`) plain SVG is written.
"""
import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_main as am  # noqa: E402

# categorical slots 1..8 of the reference palette (light surface), fixed order
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GRAY = "#8a8985"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#dcdbd6", "#ffffff"
STRUCT_COLOR = {"T0": SLOT[0], "T1": SLOT[1], "T2": SLOT[2], am.ORACLE: GRAY}
CAUSE_COLOR = dict(zip(am.CAUSE_ROWS, SLOT[:7] + [GRAY]))
FONT = "'Noto Sans CJK KR','Noto Sans KR','NanumGothic','Malgun Gothic','Apple SD Gothic Neo',sans-serif"
INT_COLUMNS = ("C", "G", "G_strict", "S", "M", "n_robots", "M_max_robot", "cap_n", "rep", "attempts", "guess_with_msg",
               "msg_decision", "msg_chance", "cap", "llm_calls") + am.PUT_COLUMNS
BOOL_COLUMNS = ("raw_C", "raw_S", "cap_reached", "first_unresolved", "complete", "control")
FRACTION_COLUMNS = tuple(am.PENALTY_LAMBDAS)


# ------------------------------------------------------------------ input
def parse_cells(path):
    """cells.csv -> typed cells in the shape analyze_main.Book reads (ints, exact Fractions for SP, lists for tags/warnings)."""
    cells = []
    with open(path, encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            cell = dict(row)
            for key in INT_COLUMNS:
                text = row.get(key, "")
                cell[key] = None if text in ("", None) else int(float(text))
            for key in FRACTION_COLUMNS:
                text = row.get(key, "")
                cell[key] = None if text in ("", None) else Fraction(text)       # decimal text -> exact (0.76 = 19/25)
            cell["tags"] = [t for t in row.get("tags", "").split("|") if t]
            cell["warnings"] = [w for w in row.get("warnings", "").split("; ") if w]
            for key in BOOL_COLUMNS:
                cell[key] = None if row.get(key, "") == "" else row[key] == "True"
            cells.append(cell)
    return cells


def load(name=None, cells_path=None, tests_path=None):
    base = HERE / "out" / name if name else None
    cells_path = Path(cells_path) if cells_path else base / "cells.csv"
    tests_path = Path(tests_path) if tests_path else base / "tests.json"
    tests = json.loads(tests_path.read_text(encoding="utf-8"))
    return parse_cells(cells_path), tests


def pick_arm(cells, meta, wanted=None):
    arms = sorted({c["arm"] for c in cells if c["structure"] in am.STRUCTS})
    if wanted:
        if wanted not in arms:
            raise SystemExit("arm %r not in cells.csv; arms with T0/T1/T2 cells: %s" % (wanted, arms))
        return wanted
    if meta.get("main_group") in arms:
        return meta["main_group"]
    raise SystemExit("main group %r has no T0/T1/T2 cells; give --arm (one of %s)" % (meta.get("main_group"), arms))


# ------------------------------------------------------------------ data prep (no drawing here)
def pct(value):
    return None if value is None else 100.0 * float(value)


def cell_counts(cells, arm, structure, interim):
    group = [c for c in cells if c["arm"] == arm and c["structure"] == structure]
    ok = [c for c in group if c["state"] == "ok"]
    return len(group), len(ok)


def note(book_means, cells, arm, structure, interim):
    total, ok = cell_counts(cells, arm, structure, interim)
    return "%d 장면\n완료 %d/%d 칸" % (len(book_means), ok, total)


def prep_a(cells, meta, arm, mode):
    book = am.Book(cells, meta["interim"], meta["plan_na"])
    sp = meta["penalty"]["primary"]
    panels, numbers = [], {}
    for metric, label in (("C", "계획 덮임 C (%)"), (sp, "메시지 벌점 점수 %s (%%)" % sp)):
        values, errs, points, notes, rows = [], [], [], [], {}
        for structure in am.STRUCTS:
            means = book.scene_means(structure, metric, mode, arm)
            scene_ids = sorted(means)
            floats = [float(means[s]) for s in scene_ids]
            mean = sum(floats) / len(floats) if floats else None
            ci = am.bootstrap_ci(floats, meta["boots"], meta["seed"]) if floats else None
            values.append(pct(mean))
            errs.append(None if ci is None else (pct(ci[0]), pct(ci[1])))
            points.append([pct(v) for v in floats])
            notes.append(note(means, cells, arm, structure, meta["interim"]))
            rows[structure] = {"n_scenes": len(floats), "mean": mean, "ci95": ci, "scenes": dict(zip(scene_ids, floats))}
        numbers[metric] = rows
        panels.append(dict(title=label, ylabel="장면 평균의 평균 (%)", ymax=100, cats=list(am.STRUCTS), notes=notes, mode="group",
                           series=[dict(name="구조 평균 (막대) · 장면 부트스트랩 95% 구간 (선) · 장면 (점)", color=None, colors=[STRUCT_COLOR[s] for s in am.STRUCTS],
                                        values=values, err=errs, points=points, label=True)]))
    foot = ["막대 = 장면 평균의 평균, 세로선 = 장면 복원추출 부트스트랩 95%% 구간(%d회, 시드 %d), 점 = 장면 점수. 실패·미완료 칸은 %s." % (
        meta["boots"], meta["seed"], {"zero": "0 으로 평균에 넣음", "drop": "뺌", "one": "1 로 넣음"}[mode])]
    return dict(title="구조별 계획 덮임과 메시지 벌점 점수", panels=panels, legend=[(s, STRUCT_COLOR[s]) for s in am.STRUCTS], foot=foot), numbers


def prep_b(cells, meta, arm, mode):
    book = am.Book(cells, meta["interim"], meta["plan_na"])
    parts_by, ns, totals, notes = {}, {}, [], []
    for structure in am.STRUCTS:
        n, parts = book.cause_partition(structure, arm)      # mode zero only (analyze_main's table 4b)
        parts_by[structure], ns[structure] = parts, n
        total, ok = cell_counts(cells, arm, structure, meta["interim"])
        totals.append(pct(sum(parts.values())))
        notes.append("%d 장면\n완료 %d/%d 칸\n부족분 %.1f" % (n, ok, total, pct(sum(parts.values()))))
    series = [dict(name=am.CAUSE_TEXT[k], color=CAUSE_COLOR[k], values=[pct(parts_by[s][k]) for s in am.STRUCTS], label=True)
              for k in am.CAUSE_ROWS]
    panel = dict(title="C 부족분(100 − C 평균)의 대표 원인 몫 (pp)", ylabel="부족분 (퍼센트포인트)", ymax=100, cats=list(am.STRUCTS), notes=notes,
                 mode="stack", series=series, w=560)
    numbers = {s: {"n_scenes": ns[s], "shortfall_pp": totals[i], "parts_pp": {k: pct(parts_by[s][k]) for k in am.CAUSE_ROWS}}
               for i, s in enumerate(am.STRUCTS)}
    note_text = "대표 꼬리표(복수 꼬리표가 아님)별 몫. 고장·미완료 칸은 꼬리표가 없어 별도 항목. 실패 칸 = 0 모드."
    if mode != "zero":
        note_text += " (이 그림은 zero 모드 고정)"
    return dict(title="부족분 원인 분해", panels=[panel], legend=[(s["name"], s["color"]) for s in series], foot=[note_text]), numbers


QUADS = (("P1/S1", "계획 맞고 물리 성공", SLOT[0]), ("P1/S0", "계획 맞고 물리 실패", SLOT[1]),
         ("P0/S1", "계획 틀리고 물리 성공", SLOT[2]), ("P0/S0", "계획 틀리고 물리 실패", SLOT[3]),
         ("plan_na", "계획 NA", SLOT[4]), ("fault", "고장·미완료(미수집 포함)", GRAY))


def quad_counts(group, interim):
    counts = Counter()
    for c in group:
        if c["state"] == "ok":
            counts["P%d/S%d" % (c["C"], c["S"])] += 1
        elif c["state"] == "plan_na":
            counts["plan_na"] += 1
        elif c["state"] == "failed" or (c["state"] == "in_progress" and not interim):
            counts["fault"] += 1
    return counts


def prep_c(cells, meta, arm, mode):
    cats, groups = [], []
    if any(c["structure"] == am.ORACLE for c in cells):
        cats.append(am.ORACLE)
        groups.append([c for c in cells if c["structure"] == am.ORACLE])
    for structure in am.STRUCTS:
        cats.append(structure)
        groups.append([c for c in cells if c["arm"] == arm and c["structure"] == structure])
    counts = [quad_counts(g, meta["interim"]) for g in groups]
    series = [dict(name=text, color=color, values=[n[key] for n in counts], label=True) for key, text, color in QUADS]
    notes = ["%d 칸" % sum(n.values()) for n in counts]
    panel = dict(title="계획 실패 대 물리 실패 (칸 수)", ylabel="칸 수", ymax=None, cats=["기준선" if c == am.ORACLE else c for c in cats],
                 notes=notes, mode="stack", series=series)
    numbers = {c: dict(n) for c, n in zip(cats, counts)}
    return dict(title="계획 실패 대 물리 실패", panels=[panel], legend=[(s["name"], s["color"]) for s in series],
                foot=["P1 = 마지막 계획이 장면 주문과 같음(C=1), S1 = 물리 성공. 기준선 = 정답 계획 고정 실행. 고장·미완료는 실패 칸과, 중간 점검 모드(--interim)가 아닐 때 아직 안 끝난 칸."]), numbers


def prep_d(cells, meta, arm, mode):
    ok = [c for c in cells if c["arm"] == arm and c["structure"] in am.STRUCTS and c["state"] == "ok"]
    known = [c for c in ok if c["M"] is not None]
    top = max([c["M"] for c in known] + [0])
    robots = sorted({c["n_robots"] for c in known if c["n_robots"]})
    caps = sorted({c["cap"] for c in known if c["cap"]})
    top = max([top] + [am.PENALTY_ALLOWANCE * r for r in robots] + caps)
    cats = list(range(top + 1))
    series, numbers = [], {}
    for structure in am.STRUCTS:
        counter = Counter(c["M"] for c in known if c["structure"] == structure)
        series.append(dict(name="%s (%d 칸)" % (structure, sum(counter.values())), color=STRUCT_COLOR[structure],
                           values=[counter[m] for m in cats]))
        numbers[structure] = {"cells": sum(counter.values()), "M_counts": {str(m): counter[m] for m in cats if counter[m]}}
    marks = [(am.PENALTY_ALLOWANCE * r + 1, "허용 2R=%d (R=%d)" % (am.PENALTY_ALLOWANCE * r, r)) for r in robots]
    unknown = len(ok) - len(known)
    panel = dict(title="실행당 보낸 메시지 수 M", ylabel="칸 수", ymax=None, cats=[str(m) for m in cats], notes=None, mode="group",
                 series=series, vmarks=marks, w=760)
    foot = ["M = 실행에서 모든 로봇이 보낸 메시지 봉투 수. 점선 오른쪽은 허용(2R)을 넘어 벌점이 붙는 칸. 완료 칸만, M 모름 %d 칸 제외." % unknown]
    if caps:
        foot.append("로봇당 상한 %s (실행 총량 상한은 로봇 수 × 상한)." % ", ".join(str(c) for c in caps))
    return dict(title="메시지 수 분포", panels=[panel], legend=[(s["name"], s["color"]) for s in series], foot=foot), numbers


def prep_e(cells, meta, arm, mode):
    book = am.Book(cells, meta["interim"], meta["plan_na"])
    panels, numbers = [], {}
    n_base = sum(1 for c in cells if c["structure"] == am.ORACLE)
    for metric, label in (("C", "계획 덮임 C"), ("S", "물리 성공 S")):
        base = book.scene_means(am.ORACLE, metric, mode)
        base_vals, struct_vals, notes, rows = [], [], [], {}
        for structure in am.STRUCTS:
            own = book.scene_means(structure, metric, mode, arm)
            common = sorted(set(own) & set(base))
            b = sum(float(base[s]) for s in common) / len(common) if common else None
            v = sum(float(own[s]) for s in common) / len(common) if common else None
            base_vals.append(pct(b))
            struct_vals.append(pct(v))
            notes.append("겹친 장면 %d" % len(common) + ("" if common else "\n(간격 계산 불가)"))
            rows[structure] = {"common_scenes": len(common), "baseline_mean": b, "structure_mean": v,
                               "gap_pp": None if b is None else pct(b - v)}
        numbers[metric] = {"baseline_scenes": len(base), "baseline_mean_all": (sum(float(x) for x in base.values()) / len(base)) if base else None,
                           "by_structure": rows}
        panels.append(dict(title="%s: 기준선 대 구조 (같은 장면만)" % label, ylabel="장면 평균의 평균 (%)", ymax=100, cats=list(am.STRUCTS),
                           notes=notes, mode="group", empty_note=None if base else "기준선 칸 없음",
                           series=[dict(name="기준선(정답 계획)", color=GRAY, values=base_vals, label=True),
                                   dict(name="구조", color=None, colors=[STRUCT_COLOR[s] for s in am.STRUCTS], values=struct_vals, label=True)]))
    foot = ["기준선 칸 %d개, 장면 %d개(정답 계획 고정 실행). 겹친 장면 = 기준선과 그 구조가 모두 점수를 가진 장면. 부족분 = 기준선 − 구조." % (
        n_base, numbers["C"]["baseline_scenes"])]
    return dict(title="기준선(정답 계획) 대비", panels=panels, legend=[("기준선", GRAY)] + [(s, STRUCT_COLOR[s]) for s in am.STRUCTS], foot=foot), numbers


FIGURES = (("fig_a_structure_means", prep_a), ("fig_b_shortfall_causes", prep_b), ("fig_c_plan_vs_physical", prep_c),
           ("fig_d_message_counts", prep_d), ("fig_e_vs_baseline", prep_e))


# ------------------------------------------------------------------ SVG drawing (standard library)
def text_width(text, size):
    return sum(size if ord(ch) >= 0x2e80 else size * 0.56 for ch in text)


def wrap(text, limit, size):
    """Greedy word wrap by estimated width (CJK chars count full size); words are split at spaces only."""
    lines, current = [], ""
    for word in text.split(" "):
        trial = (current + " " + word).strip()
        if current and text_width(trial, size) > limit:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + [current] if current else lines


def nice_ticks(top, count=5):
    if top <= 0:
        return [0, 1]
    step = top / count
    magnitude = 10 ** math.floor(math.log10(step))
    for factor in (1, 2, 2.5, 5, 10):
        if step <= factor * magnitude:
            step = factor * magnitude
            break
    ticks, value = [], 0.0
    while value <= top + 1e-9:
        ticks.append(round(value, 10))
        value += step
    if ticks[-1] < top - 1e-9:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def fmt(value):
    return ("%d" % value) if float(value).is_integer() else ("%.1f" % value)


class Canvas:
    def __init__(self):
        self.parts = []

    def add(self, markup):
        self.parts.append(markup)

    def text(self, x, y, content, size=12, anchor="start", fill=INK, weight="normal", rotate=None):
        transform = ' transform="rotate(%d %.1f %.1f)"' % (rotate, x, y) if rotate else ""
        self.add('<text x="%.1f" y="%.1f" font-size="%d" text-anchor="%s" fill="%s" font-weight="%s"%s>%s</text>'
                 % (x, y, size, anchor, fill, weight, transform, escape(str(content))))

    def lines(self, x, y, content, size, anchor, fill=INK2, leading=1.25):
        for i, line in enumerate(str(content).split("\n")):
            self.text(x, y + i * size * leading, line, size, anchor, fill)


def draw_panel(cv, p, x0, y0, width, height):
    left, right, top, bottom = 56, 14, 44, 22 + 14 * (max([len(str(n).split("\n")) for n in p["notes"]] + [1]) if p.get("notes") else 0) + 16
    px, py, pw, ph = x0 + left, y0 + top, width - left - right, height - top - bottom
    cats, series, mode = p["cats"], p["series"], p["mode"]
    ncat = len(cats)
    tops = []
    for i in range(ncat):
        vals = [s["values"][i] for s in series if s["values"][i] is not None]
        tops.append(sum(vals) if mode == "stack" else max(vals + [0]))
        for s in series:
            if mode == "group" and s.get("err") and s["err"][i]:
                tops.append(s["err"][i][1])
            if mode == "group" and s.get("points") and s["points"][i]:
                tops.append(max(s["points"][i]))
    if p.get("ymax"):
        ymax = p["ymax"]
        ticks = [t for t in nice_ticks(ymax) if t <= ymax + 1e-9]
    else:
        ticks = nice_ticks(max(tops + [1]) * 1.08)
        ymax = ticks[-1]

    def Y(v):
        return py + ph - ph * v / ymax

    cv.text(x0 + 2, y0 + 16, p["title"], 13, weight="bold")
    for t in ticks:
        cv.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>' % (px, Y(t), px + pw, Y(t), GRID))
        cv.text(px - 6, Y(t) + 4, fmt(t), 11, "end", INK2)
    cv.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.5"/>' % (px, Y(0), px + pw, Y(0), INK2))
    cv.text(x0 + 10, py + ph / 2, p["ylabel"], 11, "middle", INK2, rotate=-90)
    band = pw / ncat
    nser = len(series)
    for i, cat in enumerate(cats):
        cx = px + band * (i + 0.5)
        if mode == "stack":
            bw = min(band * 0.55, 90)
            level = 0.0
            for s in series:
                v = s["values"][i]
                if not v:
                    continue
                y1, y2 = Y(level + v), Y(level)
                cv.add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="%s" stroke-width="1.5"><title>%s: %s</title></rect>'
                       % (cx - bw / 2, y1, bw, max(0.5, y2 - y1), s["color"], SURFACE, escape(s["name"]), fmt(v)))
                if s.get("label") and y2 - y1 >= 14:
                    cv.text(cx, (y1 + y2) / 2 + 4, fmt(v), 11, "middle", "#ffffff" if s["color"] not in (SLOT[3], SLOT[4]) else INK)
                level += v
        else:
            group_w = min(band * 0.78, 56 * nser)
            bw = group_w / nser
            for j, s in enumerate(series):
                v = s["values"][i]
                if v is None:
                    continue
                color = (s.get("colors") or [s["color"]] * ncat)[i]
                bx = cx - group_w / 2 + j * bw
                cv.add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"><title>%s %s: %s</title></rect>'
                       % (bx + 1, Y(v), max(bw - 2, 1), max(Y(0) - Y(v), 0.5), color, escape(str(cat)), escape(s["name"]), fmt(v)))
                err = s.get("err") and s["err"][i]
                if err:
                    ex = bx + bw / 2
                    cv.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.5"/>' % (ex, Y(err[0]), ex, Y(err[1]), INK))
                    for e in err:
                        cv.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.5"/>' % (ex - 5, Y(e), ex + 5, Y(e), INK))
                for k, pv in enumerate(s.get("points", [[]] * ncat)[i] or []):
                    jitter = ((k * 37) % 11 - 5) * (bw * 0.05)
                    cv.add('<circle cx="%.1f" cy="%.1f" r="3.2" fill="%s" stroke="%s" stroke-width="1.5" opacity="0.9"/>' % (bx + bw / 2 + jitter + bw * 0.28, Y(pv), INK2, SURFACE))
                if s.get("label") and nser * ncat <= 24:
                    cv.text(bx + bw / 2, (Y(err[1]) if err else Y(v)) - 6, fmt(v), 11, "middle", INK)
        cv.text(cx, py + ph + 16, cat, 12, "middle", INK)
        if p.get("notes"):
            cv.lines(cx, py + ph + 31, p["notes"][i], 10, "middle")
    for mark, label in p.get("vmarks", []):
        mx = px + band * mark
        cv.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.5" stroke-dasharray="5 4"/>' % (mx, py, mx, py + ph, INK))
        cv.text(mx + 4, py + 12 + 13 * (p["vmarks"].index((mark, label))), label, 11, "start", INK)
    empty = p.get("empty_note") or (None if any(v is not None for s in series for v in s["values"]) else "자료 없음")
    if not p.get("empty_note") and p["title"].count("기준선"):
        if all(v is None for s in series for v in s["values"]):
            empty = "겹친 장면 0: 기준선과 구조가 같은 장면에서 점수를 가진 칸이 없다"
    if empty:
        cv.text(px + pw / 2, py + ph / 2, empty, 12, "middle", INK2)


def svg_figure(fig):
    panels = fig["panels"]
    widths = [p.get("w", 430) for p in panels]
    ncols = 1 if (len(panels) == 1 or max(widths) > 500) else 2
    rows = [panels[i:i + ncols] for i in range(0, len(panels), ncols)]
    row_h = 340
    width = max(sum(p.get("w", 430) for p in r) for r in rows) + 20
    legend = fig.get("legend", [])
    # legend rows
    legend_rows, cursor, row = [], 0, []
    for name, color in legend:
        w = 22 + text_width(name, 12) + 16
        if cursor + w > width - 20 and row:
            legend_rows.append(row)
            row, cursor = [], 0
        row.append((name, color, cursor))
        cursor += w
    if row:
        legend_rows.append(row)
    head = 50
    foot = []
    for line in fig.get("foot", []):
        foot.extend(wrap(line, width - 20, 11))
    height = head + len(rows) * row_h + 24 * len(legend_rows) + 18 * len(foot) + 12
    cv = Canvas()
    cv.text(10, 24, fig["title"], 16, weight="bold")
    if fig.get("note"):
        cv.text(10, 42, fig["note"], 12, fill="#b3261e", weight="bold")
    for r, row_panels in enumerate(rows):
        x = 10
        for p in row_panels:
            draw_panel(cv, p, x, head + r * row_h, p.get("w", 430), row_h)
            x += p.get("w", 430)
    y = head + len(rows) * row_h + 4
    for line in legend_rows:
        for name, color, offset in line:
            cv.add('<rect x="%.1f" y="%.1f" width="14" height="14" rx="3" fill="%s"/>' % (14 + offset, y, color))
            cv.text(34 + offset, y + 12, name, 12, fill=INK2)
        y += 24
    for line in foot:
        cv.text(10, y + 12, line, 11, fill=INK2)
        y += 18
    body = "\n".join(cv.parts)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="%s">\n'
            '<rect width="100%%" height="100%%" fill="%s"/>\n%s\n</svg>\n' % (width, height, width, height, FONT, SURFACE, body))


# ------------------------------------------------------------------ matplotlib drawing (same spec; not runnable on this server)
def mpl_figure(fig, path):  # pragma: no cover - matplotlib is not installed here (확인 안 됨)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = fig["panels"]
    out, axes = plt.subplots(1, len(panels), figsize=(sum(p.get("w", 430) for p in panels) / 100.0, 4.2), squeeze=False)
    for ax, p in zip(axes[0], panels):
        n, nser = len(p["cats"]), len(p["series"])
        xs = list(range(n))
        bottom = [0.0] * n
        for j, s in enumerate(p["series"]):
            vals = [v or 0 for v in s["values"]]
            if p["mode"] == "stack":
                ax.bar(xs, vals, 0.55, bottom=bottom, color=s["color"], label=s["name"], edgecolor="white", linewidth=1)
                bottom = [b + v for b, v in zip(bottom, vals)]
            else:
                width = 0.78 / nser
                pos = [x - 0.39 + width * (j + 0.5) for x in xs]
                colors = s.get("colors") or [s["color"]] * n
                ax.bar(pos, vals, width * 0.92, color=colors, label=None if s.get("colors") else s["name"])
                for x, e in zip(pos, s.get("err") or [None] * n):
                    if e:
                        ax.vlines(x, e[0], e[1], color="black")
                for x, pts in zip(pos, s.get("points") or [[]] * n):
                    ax.scatter([x] * len(pts), pts, s=12, color="#52514e", zorder=3)
        for mark, label in p.get("vmarks", []):
            ax.axvline(mark - 0.5, color="black", linestyle="--")
            ax.text(mark - 0.45, ax.get_ylim()[1] * 0.95, label, fontsize=8)
        labels = ["%s\n%s" % (c, (p["notes"][i] if p.get("notes") else "")) for i, c in enumerate(p["cats"])]
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(p["title"], fontsize=10)
        ax.set_ylabel(p["ylabel"])
        if p.get("ymax"):
            ax.set_ylim(0, p["ymax"])
    out.suptitle(fig["title"] + ("  [%s]" % fig["note"] if fig.get("note") else ""))
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in fig.get("legend", [])]
    out.legend(handles, [n for n, _ in fig.get("legend", [])], loc="lower center", ncol=4, fontsize=8)
    out.tight_layout(rect=(0, 0.1, 1, 0.95))
    out.savefig(path)
    plt.close(out)


# ------------------------------------------------------------------ main
def make(name=None, cells_path=None, tests_path=None, out=None, arm=None, mode="zero", backend="auto", note=""):
    cells, tests = load(name, cells_path, tests_path)
    meta = tests["meta"]
    arm = pick_arm(cells, meta, arm)
    out = Path(out) if out else (HERE / "out" / name / "figures")
    out.mkdir(parents=True, exist_ok=True)
    use_mpl = False
    if backend in ("auto", "matplotlib"):
        try:
            import matplotlib  # noqa: F401
            use_mpl = True
        except ImportError:
            if backend == "matplotlib":
                raise SystemExit("matplotlib is not installed; use --backend svg")
    written, numbers = [], {"arm": arm, "mode": mode, "meta": {k: meta[k] for k in ("main_group", "interim", "plan_na", "seed", "boots")},
                            "backend": "matplotlib" if use_mpl else "svg"}
    for stem, prep in FIGURES:
        fig, nums = prep(cells, meta, arm, mode)
        fig["note"] = note
        numbers[stem] = nums
        if use_mpl:
            path = out / (stem + ".pdf")
            mpl_figure(fig, path)
        else:
            path = out / (stem + ".svg")
            path.write_text(svg_figure(fig), encoding="utf-8")
        written.append(path)
    (out / "figures.json").write_text(json.dumps(numbers, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="analyze_main --name (reads out/NAME/cells.csv and tests.json)")
    parser.add_argument("--cells", type=Path)
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--out", type=Path, help="default out/NAME/figures")
    parser.add_argument("--arm", help="default: the main group of the analysis")
    parser.add_argument("--mode", choices=am.MODES, default="zero")
    parser.add_argument("--backend", choices=("auto", "svg", "matplotlib"), default="auto")
    parser.add_argument("--note", default="", help="red banner on every figure (e.g. '예행연습, 결과 아님')")
    args = parser.parse_args(argv)
    if not args.name and not (args.cells and args.tests and args.out):
        parser.error("give --name, or --cells, --tests and --out")
    for path in make(args.name, args.cells, args.tests, args.out, args.arm, args.mode, args.backend, args.note):
        print(path)


if __name__ == "__main__":
    main()
