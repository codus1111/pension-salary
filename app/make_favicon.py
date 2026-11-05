"""브라우저 탭 아이콘(app/static/favicon.png) 만들기. 사이트 첫 화면과 같은 파란색 둥근 네모 + 오르는 막대 3개.

사용법 (WSL): ~/venvs/pension/bin/python app/make_favicon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 256  # 크게 그린 뒤 줄여서 가장자리를 매끄럽게
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 배경: 위 밝은 파랑 → 아래 진한 파랑
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
top, bottom = (77, 151, 255), (5, 80, 192)
for y in range(S):
    t = y / (S - 1)
    gd.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=60, fill=255)
img.paste(grad, (0, 0), mask)

# 오르는 막대 3개 (연봉 비교 그래프 느낌)
w, gap, base = 42, 22, 196
x0 = (S - (3 * w + 2 * gap)) // 2
for i, h in enumerate((58, 96, 136)):
    x = x0 + i * (w + gap)
    d.rounded_rectangle([x, base - h, x + w, base], radius=12, fill=(255, 255, 255, 255 if i == 2 else 215))

out = Path(__file__).parent / "static" / "favicon.png"
img.resize((128, 128), Image.LANCZOS).save(out)
print("저장:", out)
