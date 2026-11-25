"""Draw the enrolled source's converted room geometry and target multiplicities to scale."""
from PIL import Image, ImageDraw, ImageFont

from rooms3.maps import ROBOTS


def draw(scene, out):
    image = Image.new("RGB", (1160, 538), "#fafafa")
    pen = ImageDraw.Draw(image)
    ink, muted, wall = "#182733", "#516575", "#344955"
    paint = {"red": "#cc493d", "blue": "#2965ba"}
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    def label(xy, text, size=15, colour=ink, strong=False, anchor="la"):
        try:
            font = ImageFont.truetype(bold if strong else regular, size)
        except OSError:
            font = ImageFont.load_default()
        pen.text(xy, text, fill=colour, font=font, anchor=anchor)

    lo, hi, south, north = scene["bounds"]
    scale = min(1064 / (hi - lo), 326 / (north - south))

    def xy(x, y):
        return (round(580 + scale * x), round(271 - scale * y))

    label((43, 19), f"Three rooms   /   BoxNet seed {scene['source']['seed']}", 25, strong=True)
    label((44, 58), f"1 × 3   ·   {scene['source']['map_set']}   ·   {len(scene['boxes'])} boxes"
          f"   ·   {scene['rules']['door_width']:.2f} m doors", 16, muted)
    pen.rectangle([xy(lo, north), xy(hi, south)], fill="#f2f4f2", outline=wall, width=4)
    for rid in ROBOTS:
        room = scene["rooms"][rid]
        x, y, _ = room["start"]
        label(xy(x, north - .10), f"{rid.upper()}   [{room['cell'].replace('_', ', ')}]",
              15, strong=True, anchor="ma")
        u, v = xy(x, y)
        pen.rounded_rectangle((u-12, v-12, u+12, v+11), radius=4, fill=wall)
        pen.polygon([(u-7, v+14), (u+7, v+14), (u, v+21)], fill=wall)
        sign = scene["signs"][str(room["sign"])]
        left, right, near, far = sign["area"]
        pen.rectangle([xy(left, far), xy(right, near)], fill="#dfe9dd", outline="#81967d")
        u, v = xy(*sign["pos"])
        pen.rectangle((u-9, v-9, u+9, v+8), fill="#28392f")
        label((u, v+13), f"Sign {room['sign']}", 12, strong=True, anchor="ma")
        for j, colour in enumerate(sign["targets"]):
            dx = (j - (len(sign["targets"]) - 1) / 2) * 15
            pen.ellipse((u+dx-5, v-31, u+dx+5, v-21), fill=paint[colour])
    half = scene["rules"]["door_width"] / 2
    for rid in ROBOTS[:-1]:
        x = scene["rooms"][rid]["bounds"][1]
        pen.line([xy(x, north), xy(x, half)], fill=wall, width=5)
        pen.line([xy(x, -half), xy(x, south)], fill=wall, width=5)
    for pad in scene["pads"].values():
        x, y = xy(*pad["xy"])
        direction = 1 if pad["to"] > pad["from"] else -1
        pen.rectangle((x-12, y-7, x+12, y+7), outline="#8c7463", width=2)
        pen.line((x-6*direction, y, x+6*direction, y), fill="#674c38", width=2)
        pen.polygon([(x+8*direction, y), (x+2*direction, y-4), (x+2*direction, y+4)], fill="#674c38")
    for box in scene["boxes"]:
        u, v = xy(*box["start"][:2])
        pen.rectangle((u-8, v-8, u+8, v+8), fill=paint[box["colour"]], outline=ink)
        label((u, v+10), box["id"].replace("box_", "B"), 12, anchor="ma")
    label((44, 467), "■  Box     ▼  Robot heading     →  Directional door pad     ●  Target at the numbered sign",
          16, muted)
    rules = scene["rules"]
    label((44, 501), f"Room  {rules['room_length']:.2f} × {rules['room_width']:.2f} m"
          f"      Pad capacity  {rules['pad_capacity']}      Source SHA-256  {scene['source']['sha256'][:16]}",
          14, muted)
    image.save(out, "PNG")
