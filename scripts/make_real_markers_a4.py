#!/usr/bin/env python3
"""Print-ready A4 PDF of every ArUco marker the simulation uses, at true size, for the real robots.

Sizes, numbers and heights are read from the simulation code itself (harness/robot_tags_v1.py for the destination
signs and the robot side cards, harness/overhead_v1.py for the ceiling-camera top cards), so the printout matches
what the simulated cameras see. Markers are drawn as vector squares (no image scaling), in the plain reading
direction: the simulator stores some textures mirrored only to undo MuJoCo's texture mapping, and on a real card the
plain drawing is what a camera sees from outside.

Usage:
    python3 scripts/make_real_markers_a4.py OUT.pdf [--robots 3] [--signs 11 12 13 14 15]

Needs opencv-contrib-python(-headless) and reportlab; a Korean TTF font (NanumGothic) for the captions.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from harness import overhead_v1 as top  # noqa: E402
from harness import robot_tags_v1 as tags  # noqa: E402

DICT_NAME = 'DICT_4X4_50'
PAGE_W, PAGE_H = A4
FONT, FONT_B = 'Helvetica', 'Helvetica-Bold'


def _fonts():
    global FONT, FONT_B
    for reg, bold in (('/usr/share/fonts/truetype/nanum/NanumGothic.ttf', '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'),
                      ('/Library/Fonts/NanumGothic.ttf', '/Library/Fonts/NanumGothicBold.ttf'),
                      ('C:/Windows/Fonts/malgun.ttf', 'C:/Windows/Fonts/malgunbd.ttf')):
        if Path(reg).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont('K', reg))
            pdfmetrics.registerFont(TTFont('KB', bold))
            FONT, FONT_B = 'K', 'KB'
            return
    print('warning: no Korean font found, captions may not render', file=sys.stderr)


def marker_bits(number):
    """6x6 cells (4x4 data + black border), True = black."""
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_NAME))
    img = cv2.aruco.generateImageMarker(d, number, 6)
    return img < 128


def draw_marker(c, number, x, y, side):
    """Marker with its black outer square side `side` (points), lower-left corner at (x, y)."""
    bits = marker_bits(number)
    cell = side / 6.0
    c.setFillColorRGB(0, 0, 0)
    for r in range(6):
        for col in range(6):
            if bits[r, col]:
                c.rect(x + col * cell, y + (5 - r) * cell, cell, cell, stroke=0, fill=1)


def cut_box(c, x, y, w, h):
    c.saveState()
    c.setStrokeColorRGB(0.55, 0.55, 0.55)
    c.setLineWidth(0.4)
    c.setDash(2, 2)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.restoreState()


def crop_marks(c, x, y, w, h, gap=2 * mm, length=6 * mm):
    """Corner ticks outside a rectangle (for cutting a card larger than the printed area allows)."""
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.3)
    for cx, sx in ((x, -1), (x + w, 1)):
        for cy, sy in ((y, -1), (y + h, 1)):
            c.line(cx + sx * gap, cy, cx + sx * (gap + length), cy)
            c.line(cx, cy + sy * gap, cx, cy + sy * (gap + length))
    c.restoreState()


def scale_bar(c, x, y, length_mm=100):
    c.saveState()
    c.setLineWidth(0.6)
    c.line(x, y, x + length_mm * mm, y)
    for i in range(0, length_mm + 1, 10):
        t = 3 * mm if i % 50 == 0 else 1.6 * mm
        c.line(x + i * mm, y, x + i * mm, y + t)
    c.setFont(FONT, 7)
    c.drawString(x, y - 3.2 * mm, '0')
    c.drawRightString(x + length_mm * mm, y - 3.2 * mm, '%d mm  (자로 재서 정확히 %d mm 이어야 함)' % (length_mm, length_mm))
    c.restoreState()


def footer(c, text):
    c.setFont(FONT, 7)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawString(12 * mm, 8 * mm, text)
    c.drawRightString(PAGE_W - 12 * mm, 8 * mm, 'A4 · 100%% 실제 크기 인쇄 (페이지 맞춤 끄기) · ArUco %s' % DICT_NAME)
    c.setFillColorRGB(0, 0, 0)


# ---------------------------------------------------------------- numbers and sizes from the simulation
def sign_spec():
    card = tags.SIGN_M
    return {'card_mm': card * 1000, 'marker_mm': tags.SIGN_MARKER_M * 1000,
            'centre_h_mm': tags.SIGN_CENTRE_Z * 1000, 'bottom_h_mm': (tags.SIGN_CENTRE_Z - card / 2) * 1000}


def robot_cards(robot):
    """[(label, number, card side mm, marker side mm, mounting note)] for one robot."""
    out = []
    names = {'back': '뒤', 'left': '왼쪽', 'right': '오른쪽', 'front': '앞 범퍼'}
    for side, (_, centre, half_w, _, _, _) in tags.SIDES.items():
        card = 2 * half_w
        h = (tags.BASE_Z + centre[2]) * 1000
        note = '바닥에서 카드 중심 %.0f mm' % h if side != 'front' else '앞 범퍼 판 위, 바닥에서 약 %.0f mm' % h
        out.append(('%s 옆면' % names[side] if side in ('left', 'right') else names[side], tags.tag_number(robot, side),
                    card * 1000, card * tags.INNER * 1000, note))
    n = top.TOP_ID0 - 1 + robot
    out.append(('천장 카메라용 윗면', n, top.CARD_M * 1000, top.CARD_M * 0.75 * 1000,
                '수평, 바닥에서 %.0f mm (기둥 위), 오른쪽(▶) = 로봇 앞' % ((top.BASE_Z + top.CARD_AT[2]) * 1000)))
    return out


# ---------------------------------------------------------------- pages
def guide_page(c, robots, signs):
    s = sign_spec()
    c.setFont(FONT_B, 17)
    c.drawString(18 * mm, PAGE_H - 22 * mm, 'UGRP 실물 마커 인쇄·부착 안내')
    c.setFont(FONT, 9)
    c.drawString(18 * mm, PAGE_H - 29 * mm, '시뮬레이션 코드(harness/robot_tags_v1.py, harness/overhead_v1.py)의 값 그대로. 로봇 %d대 기준.' % robots)
    y = PAGE_H - 40 * mm

    def head(t):
        nonlocal y
        c.setFont(FONT_B, 11.5)
        c.drawString(18 * mm, y, t)
        y -= 6 * mm

    def line(t, indent=0, size=9):
        nonlocal y
        c.setFont(FONT, size)
        c.drawString((20 + indent) * mm, y, t)
        y -= 4.9 * mm

    head('1. 인쇄')
    line('• 프린터 설정에서 "실제 크기 / 100% / 배율 없음"을 고르고 "페이지에 맞춤"은 끕니다.')
    line('• 인쇄 후 각 쪽 아래의 100 mm 눈금자를 자로 재서 100 mm 인지 확인합니다 (±1 mm 넘으면 다시 인쇄).')
    line('• 무광 흰 종이(또는 무광 라벨지)에 흑백으로. 광택지는 조명 반사로 인식이 떨어집니다.')
    line('• 검은 사각형 한 변 길이가 아래 표의 "표식" 값과 같아야 합니다. 카메라가 거리를 이 값으로 계산합니다.')
    y -= 2 * mm

    head('2. 무엇이 몇 장인가 (ArUco %s, 번호는 시뮬과 같음)' % DICT_NAME)
    rows = [('종류', '번호', '카드(흰 테두리 포함)', '검은 표식 한 변', '용도'),
            ('목적지 표식', '%d–%d' % (min(signs), max(signs)), '%.0f × %.0f mm' % (s['card_mm'], s['card_mm']),
             '%.1f mm' % s['marker_mm'], '상자 내려놓을 곳'),
            ('로봇 뒤·왼·오른 면', '20 + 4(n−1) + 0/1/2', '48 × 48 mm', '36.0 mm', '로봇 이름표'),
            ('로봇 앞 범퍼', '20 + 4(n−1) + 3', '28 × 28 mm', '21.0 mm', '로봇 이름표(작음)'),
            ('로봇 윗면', '39 + n', '%.0f × %.0f mm' % (top.CARD_M * 1000, top.CARD_M * 1000),
             '%.2f mm' % (top.CARD_M * 750), '천장 카메라 위치 측정')]
    xs = [20, 50, 88, 125, 157]
    for i, r in enumerate(rows):
        c.setFont(FONT_B if i == 0 else FONT, 8.2)
        for x, t in zip(xs, r):
            c.drawString(x * mm, y, t)
        y -= 4.6 * mm
    rob = ', '.join('r%d = %s' % (n, '/'.join(str(tags.tag_number(n, sd)) for sd in tags.SIDES) + ' · 윗면 %d' % (top.TOP_ID0 - 1 + n))
                    for n in range(1, robots + 1))
    line('로봇별 번호(뒤/왼/오른/앞): ' + rob, size=8)
    y -= 2 * mm

    head('3. 붙이는 위치와 높이 (시뮬과 맞춤)')
    line('• 목적지 표식: 25 × 25 cm 흰 판(폼보드 등) 가운데에 붙여, 벽에 세웁니다. 판 아래 끝은 바닥에서 %.0f mm,' % s['bottom_h_mm'])
    line('  표식 중심은 바닥에서 %.0f mm. 방 안쪽을 향하게 똑바로(위 화살표가 위) 세웁니다.' % s['centre_h_mm'], 0)
    line('  A4 폭(210 mm)이 판(250 mm)보다 좁으므로 위·아래 재단 표시에 맞춰 자르고 흰 판에 붙입니다.', 0)
    line('• 상자 내려놓는 자리: 표식 앞 바닥, 벽에서 0.65 m 안, 표식 중심 좌우 0.5 m 안이면 배달로 칩니다.')
    line('• 로봇 옆면 카드: 뒤쪽 제어보드 케이스의 뒤·왼·오른 면 바깥에 평평하게, 카드 중심이 바닥에서 약 76 mm.')
    line('  케이스 옆면 높이가 51 mm 이므로 48 mm 카드가 그 안에 들어갑니다. 앞 카드는 앞 범퍼 판에 붙입니다.', 0)
    line('• 로봇 윗면 카드: 뒤 케이스 위에 가는 기둥을 세워, 카드 중심이 바닥에서 약 %.0f mm 인 곳에 수평으로.' % ((top.BASE_Z + top.CARD_AT[2]) * 1000))
    line('  팔을 들어도 가리지 않는 높이입니다. 위에서 볼 때 카드의 오른쪽(▶ 표시)이 로봇의 앞을 향하게 붙입니다.', 0)
    line('  (천장 판독기는 표식 윗변의 왼쪽→오른쪽 방향을 로봇 진행 방향으로 읽습니다. overhead_v1.OverheadReader)', 0, size=8)
    line('• 천장 카메라: 경기장 가운데 위 약 %.1f m, 바로 아래를 보게 설치(시뮬 값, 실제 카메라에 맞게 한 번 보정).' % top.HEIGHT_M)
    y -= 2 * mm

    head('4. 붙이지 않는 것')
    line('• 상자(화물)에는 표식을 붙이지 않습니다. 상자는 색(빨강·파랑)으로만 봅니다 (시뮬과 같음).')
    line('• 벽·문에는 이 실험에서 표식이 없습니다. 로봇은 목적지 표식으로 위치를 계산하지 않습니다.')
    y -= 2 * mm

    head('5. 붙인 뒤 확인')
    line('• 표식이 휘거나 들뜨지 않게 판·카드 전체를 평평하게 붙입니다 (휘면 거리 계산이 틀립니다).')
    line('• 흰 테두리를 자르지 마세요. 검은 사각형 바깥의 흰 여백이 있어야 인식됩니다.')
    line('• 같은 번호가 두 장 있으면 안 됩니다. 남는 장은 치워 두세요.')
    line('• 확인: 로봇 손목 카메라로 1 m 앞 목적지 표식을 찍어 번호가 읽히는지, 천장 카메라로 세 로봇이 다 보이는지.')
    scale_bar(c, 18 * mm, 18 * mm)
    footer(c, '안내 1/1')
    c.showPage()


def sign_page(c, number, idx, total):
    s = sign_spec()
    m = s['marker_mm'] * mm
    card = s['card_mm'] * mm
    x = (PAGE_W - m) / 2
    card_y = PAGE_H - 13 * mm - card
    y = card_y + (card - m) / 2
    draw_marker(c, number, x, y, m)
    # the card's top and bottom edges fit on A4; its left and right edges do not (paper is 210 mm wide)
    c.saveState()
    c.setStrokeColorRGB(0.55, 0.55, 0.55)
    c.setLineWidth(0.4)
    c.setDash(2, 2)
    c.line(0, card_y, PAGE_W, card_y)
    c.line(0, card_y + card, PAGE_W, card_y + card)
    c.restoreState()
    c.setFont(FONT_B, 11)
    c.drawCentredString(PAGE_W / 2, card_y + card + 3.5 * mm, '▲ 위')
    c.setFont(FONT_B, 13)
    c.drawString(14 * mm, card_y - 6.5 * mm, '목적지 표식 %d' % number)
    c.setFont(FONT, 8)
    c.drawString(14 * mm, card_y - 11 * mm,
                 '검은 사각형 %.1f mm · 판 %.0f × %.0f mm(점선 = 판 위·아래 끝) · 표식 중심 바닥에서 %.0f mm' %
                 (s['marker_mm'], s['card_mm'], s['card_mm'], s['centre_h_mm']))
    scale_bar(c, 14 * mm, 16 * mm)
    footer(c, '목적지 표식 %d/%d' % (idx, total))
    c.showPage()


def robot_page(c, robot):
    cards = robot_cards(robot)
    c.setFont(FONT_B, 15)
    c.drawString(16 * mm, PAGE_H - 20 * mm, '로봇 r%d 번호 카드 (%d장)' % (robot, len(cards)))
    c.setFont(FONT, 8.5)
    c.drawString(16 * mm, PAGE_H - 26 * mm, '점선을 따라 자릅니다. 점선 = 카드 끝(흰 테두리 포함). 흰 테두리는 자르지 마세요.')
    # cards in a grid, the label under each card
    slots = [(16, 42), (82, 42), (148, 42), (16, 125), (82, 125)]
    for (label, number, card_mm, marker_mm, note), (sx, top_mm) in zip(cards, slots):
        card = card_mm * mm
        cx, cy = sx * mm + 4 * mm, PAGE_H - top_mm * mm - card
        cut_box(c, cx, cy, card, card)
        pad = (card - marker_mm * mm) / 2
        draw_marker(c, number, cx + pad, cy + pad, marker_mm * mm)
        c.setFont(FONT_B, 10.5)
        c.drawString(cx, cy - 5.5 * mm, '%s · 번호 %d' % (label, number))
        c.setFont(FONT, 7.5)
        c.drawString(cx, cy - 10 * mm, '카드 %.0f mm · 검은 사각형 %.2f mm' % (card_mm, marker_mm))
        c.drawString(cx, cy - 14 * mm, note)
        if number >= top.TOP_ID0:
            # OverheadReader takes the marker's top edge, left to right, as the heading: the marker's right side is the front
            c.setFont(FONT_B, 9)
            c.drawCentredString(cx + card / 2, cy + card + 2 * mm, '▲ 위 (윗변)')
            c.saveState()
            c.translate(cx + card + 3 * mm, cy + card / 2)
            c.rotate(-90)
            c.drawCentredString(0, 0, '▲ 로봇 앞 (진행 방향)')
            c.restoreState()
        else:
            c.setFont(FONT, 7)
            c.drawCentredString(cx + card / 2, cy + card + 1.5 * mm, '▲ 위')
    scale_bar(c, 16 * mm, 18 * mm)
    footer(c, '로봇 r%d' % robot)
    c.showPage()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('out', type=Path)
    ap.add_argument('--robots', type=int, default=3)
    ap.add_argument('--signs', type=int, nargs='+', default=[11, 12, 13, 14, 15])
    a = ap.parse_args()
    if not 1 <= a.robots <= 5:
        ap.error('robot side-card numbers 20..47 collide with the top cards (40+) beyond 5 robots; use <= 5')
    used = [n for r in range(1, a.robots + 1) for n in tags.robot_tag_numbers((r,))] + top.card_numbers(['r%d' % r for r in range(1, a.robots + 1)])
    clash = sorted(set(a.signs) & set(used)) + sorted({n for n in used if used.count(n) > 1})
    if clash or any(n >= 50 for n in a.signs + used):
        ap.error('marker numbers clash or exceed %s: %s' % (DICT_NAME, clash))
    _fonts()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(a.out), pagesize=A4)
    c.setTitle('UGRP real-robot ArUco markers (A4, 1:1)')
    guide_page(c, a.robots, a.signs)
    for i, n in enumerate(a.signs, 1):
        sign_page(c, n, i, len(a.signs))
    for r in range(1, a.robots + 1):
        robot_page(c, r)
    c.save()
    print(a.out)


if __name__ == '__main__':
    main()
