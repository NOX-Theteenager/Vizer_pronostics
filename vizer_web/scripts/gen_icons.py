#!/usr/bin/env python3
"""
Génère les icônes PWA de Vizer depuis le tracé du « V » de la maquette.

Le logo d'origine (VizerLogo.png) est un « V » néon : une lame verte et une
lame argentée qui se rejoignent en pointe. Il est redessiné ici en primitives
Pillow — aucune ressource externe, et la même géométrie que <VizerMark>.

Sorties (public/icons/) :
    icon-192.png · icon-512.png · icon-maskable-512.png · apple-touch-icon.png

Usage : python3 scripts/gen_icons.py
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

BG = (11, 13, 18)            # --bg #0b0d12
GREEN_TOP = (79, 240, 154)   # #4ff09a
GREEN_BOT = (19, 179, 106)   # #13b36a
SILVER_TOP = (233, 238, 245) # #e9eef5
SILVER_BOT = (154, 166, 182) # #9aa6b6

SS = 4  # supersampling
OUT = pathlib.Path(__file__).resolve().parent.parent / 'public' / 'icons'


def _vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    grad = Image.new('RGB', (1, size))
    px = grad.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((size, size))


def _blade(size: int, inset: float, side: str) -> Image.Image:
    """Masque d'une des deux lames du V."""
    mask = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(mask)
    box = size * (1 - 2 * inset)
    x0 = y0 = size * inset

    def p(fx: float, fy: float) -> tuple[float, float]:
        return (x0 + box * fx, y0 + box * fy)

    if side == 'left':
        pts = [p(0.00, 0.00), p(0.27, 0.00), p(0.55, 0.86), p(0.44, 1.00)]
    else:
        pts = [p(1.00, 0.00), p(0.73, 0.00), p(0.45, 0.86), p(0.56, 1.00)]
    d.polygon(pts, fill=255)
    return mask


def render(size: int, inset: float, rounded: bool) -> Image.Image:
    big = size * SS
    canvas = Image.new('RGB', (big, big), BG)
    canvas.paste(_vertical_gradient(big, GREEN_TOP, GREEN_BOT), (0, 0), _blade(big, inset, 'left'))
    canvas.paste(_vertical_gradient(big, SILVER_TOP, SILVER_BOT), (0, 0), _blade(big, inset, 'right'))

    img = canvas.resize((size, size), Image.LANCZOS).convert('RGBA')

    if rounded:
        corner = Image.new('L', (big, big), 0)
        ImageDraw.Draw(corner).rounded_rectangle(
            [0, 0, big - 1, big - 1], radius=round(big * 0.22), fill=255
        )
        img.putalpha(corner.resize((size, size), Image.LANCZOS))

    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, inset, rounded in [
        ('icon-192.png', 192, 0.16, False),
        ('icon-512.png', 512, 0.16, False),
        ('icon-maskable-512.png', 512, 0.27, False),
        ('apple-touch-icon.png', 180, 0.16, True),
    ]:
        render(size, inset, rounded).save(OUT / name, optimize=True)
        print(f'  ✓ {name}')


if __name__ == '__main__':
    main()
