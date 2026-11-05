"""사이트 아이콘(app/static/favicon.png) 만들기: 첫 화면의 파란 유리 구슬을 닮은 공 + 가운데 흰 ₩(연봉).

탭 아이콘과 왼쪽 위 로고에 같이 쓴다. 16px로 줄어도 보이게 모양은 단순하게(공 + 굵은 ₩)만 둔다.
사용법 (WSL): ~/venvs/pension/bin/python app/make_favicon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 512  # 크게 그린 뒤 줄여서 가장자리를 매끄럽게
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# 1) 공: 왼쪽 위가 밝고 오른쪽 아래가 진한 파랑 (첫 화면 구슬 색 #5b9bff → #0550c0)
ball = Image.new("RGBA", (S, S))
px = ball.load()
cx, cy, r = S / 2, S / 2, S * 0.47
lx, ly = S * 0.34, S * 0.30  # 빛이 들어오는 쪽
light, dark = (120, 178, 255), (4, 70, 176)
for y in range(S):
    for x in range(S):
        d = ((x - lx) ** 2 + (y - ly) ** 2) ** 0.5 / (S * 0.82)
        t = min(1.0, d)
        px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(light, dark)) + (255,)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
img.paste(ball, (0, 0), mask)

# 2) 유리 느낌의 하이라이트 (왼쪽 위 흰 타원, 흐리게)
hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(hl).ellipse([S * 0.20, S * 0.12, S * 0.52, S * 0.34], fill=(255, 255, 255, 120))
img = Image.alpha_composite(img, hl.filter(ImageFilter.GaussianBlur(S * 0.03)))

# 3) 가운데 흰 ₩: 굵은 W 꺾은선 + 가로줄 두 개
d = ImageDraw.Draw(img)
w = int(S * 0.075)
top, bot = S * 0.33, S * 0.68
xs = [S * 0.28, S * 0.385, S * 0.5, S * 0.615, S * 0.72]
pts = [(xs[0], top), (xs[1], bot), (xs[2], top + S * 0.08), (xs[3], bot), (xs[4], top)]
d.line(pts, fill="white", width=w, joint="curve")
for (x, y) in (pts[0], pts[-1], pts[1], pts[3]):
    d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill="white")
for yy in (S * 0.47, S * 0.555):
    d.rounded_rectangle([S * 0.24, yy - w * 0.32, S * 0.76, yy + w * 0.32], radius=w * 0.3, fill="white")

out = Path(__file__).parent / "static" / "favicon.png"
img.resize((128, 128), Image.LANCZOS).save(out)
print("저장:", out)
