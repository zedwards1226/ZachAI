"""Generate a 1024x1024 lightning-bolt app icon (yellow bolt on black).

Output: assets/icon/lightning_bolt.png
"""
from PIL import Image, ImageDraw
from pathlib import Path

SIZE = 1024
OUT = Path(__file__).parent.parent / "assets" / "icon" / "lightning_bolt.png"

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
draw = ImageDraw.Draw(img)

# Centered lightning bolt polygon, yellow, ~60% of canvas.
# Bolt is a 7-point zigzag.
cx, cy = SIZE / 2, SIZE / 2
scale = SIZE * 0.42
# Normalized bolt points, origin center.
points_norm = [
    (0.10, -1.00),
    (-0.55, 0.05),
    (-0.10, 0.05),
    (-0.35, 1.00),
    (0.55, -0.10),
    (0.10, -0.10),
    (0.40, -1.00),
]
pts = [(cx + x * scale, cy + y * scale) for (x, y) in points_norm]
draw.polygon(pts, fill=(255, 235, 59, 255))  # Material Yellow 500

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT, "PNG")
print(f"Wrote {OUT} ({SIZE}x{SIZE})")
