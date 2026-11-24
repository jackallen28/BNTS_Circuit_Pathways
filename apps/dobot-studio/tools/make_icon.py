"""Draw assets/dobot-studio.png: the app and desktop icon, in the BNTS teal and purple.

Run from apps/dobot-studio: python tools/make_icon.py   (needs Pillow)
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUTPUT = Path("assets/dobot-studio.png")
SIZE, SCALE = 256, 4          # drawn four times larger, then reduced, so the edges are smooth
TEAL, PURPLE = (25, 193, 202), (112, 73, 136)
WHITE = (255, 255, 255)


def mix(a, b, fraction):
    return tuple(round(x * (1 - fraction) + y * fraction) for x, y in zip(a, b))


def tile(size):
    """A rounded square that runs from teal at the top left to purple at the bottom right."""
    gradient = Image.new("RGB", (size, size))
    pixels = gradient.load()
    for y in range(size):
        for x in range(size):
            pixels[x, y] = mix(TEAL, PURPLE, (x + y) / (2 * size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.2, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(gradient, mask=mask)
    return out, mask


def arm(draw, size):
    """The Dobot: a base, a column, two links, and a suction cup over a small mat."""
    u = size / 256
    point = lambda x, y: (x * u, y * u)
    # the mat, with a circle on it
    draw.rounded_rectangle((38 * u, 196 * u, 218 * u, 226 * u), radius=6 * u, fill=(255, 255, 255, 215))
    draw.ellipse((150 * u, 201 * u, 190 * u, 221 * u), fill=(60, 40, 90, 255))
    # the base and column
    draw.rounded_rectangle((52 * u, 168 * u, 118 * u, 192 * u), radius=8 * u, fill=WHITE)
    draw.line([point(85, 170), point(85, 118)], fill=WHITE, width=round(24 * u))
    # the lower arm and forearm
    draw.line([point(85, 118), point(135, 64)], fill=WHITE, width=round(20 * u))
    draw.line([point(135, 64), point(170, 112)], fill=WHITE, width=round(18 * u))
    # the tool and its suction cup
    draw.line([point(170, 112), point(170, 168)], fill=WHITE, width=round(11 * u))
    draw.rounded_rectangle((156 * u, 166 * u, 184 * u, 180 * u), radius=5 * u, fill=WHITE)
    # the joints, in the tile's own colours
    for x, y, r in ((85, 118, 11), (135, 64, 11), (170, 112, 9)):
        draw.ellipse(((x - r) * u, (y - r) * u, (x + r) * u, (y + r) * u), fill=(60, 40, 90, 255))
        draw.ellipse(((x - r * 0.45) * u, (y - r * 0.45) * u, (x + r * 0.45) * u, (y + r * 0.45) * u), fill=WHITE)


def icon(size=SIZE * SCALE):
    base, mask = tile(size)
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    arm_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    arm(ImageDraw.Draw(arm_layer), size)
    shadow.paste((20, 10, 40, 110), mask=arm_layer.split()[3].filter(ImageFilter.GaussianBlur(size * 0.012)))
    base = Image.alpha_composite(base, ImageChops.offset(shadow, round(size * 0.008), round(size * 0.014)))
    base = Image.alpha_composite(base, arm_layer)
    # a glossy highlight over the top half, like the Vista buttons
    gloss = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse((-size * 0.25, -size * 0.62, size * 1.25, size * 0.42), fill=(255, 255, 255, 52))
    gloss.putalpha(ImageChops.multiply(gloss.split()[3], mask))
    base = Image.alpha_composite(base, gloss)
    rim = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.2, outline=(255, 255, 255, 120),
                                          width=round(size * 0.012))
    return Image.alpha_composite(base, rim)


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    icon().resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(OUTPUT, optimize=True)


if __name__ == "__main__":
    main()
