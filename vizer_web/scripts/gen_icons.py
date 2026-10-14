#!/usr/bin/env python3
"""
Génère les icônes PWA et la marque de l'app depuis `assets/VizerLogo.png`.

Le fichier fourni est un rendu carré : le « V » néon sur un fond gris-vert
opaque, avec une lueur. L'app en a besoin sur deux thèmes et sur des fonds
variés, donc on en extrait une version à fond transparent.

Comment le fond est retiré
--------------------------
Pas de seuil sur une couleur : la lame argentée est claire et peu saturée, le
ballon est sombre et neutre — l'un comme l'autre ressemblent au fond sur un
seul critère. On estime donc le fond par un flou très large, puis on garde les
pixels qui s'en écartent, *ou* qui l'assombrissent (c'est ce qui sauve le
ballon). La lueur, elle, est de la lumière **sur** du gris : un pixel vaut
`alpha·F + (1-alpha)·fond`, donc on retrouve `F` au lieu de conserver un gris
translucide qui ferait un voile sale sur fond clair.

Sorties :
    public/icons/icon-192.png
    public/icons/icon-512.png
    public/icons/icon-maskable-512.png
    public/icons/apple-touch-icon.png
    public/icons/icon.png            ← favicon
    src/assets/vizer-logo.png        ← marque transparente, importée par l'app

Usage : python3 scripts/gen_icons.py
"""
from __future__ import annotations

import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'assets' / 'VizerLogo.png'
ICONS = ROOT / 'public' / 'icons'
APP_ASSETS = ROOT / 'src' / 'assets'

BG = (11, 13, 18)   # --bg #0b0d12, fond des icônes pleines

# Seuils du matte, en distance au fond estimé. En dessous de LO le pixel est
# du fond, au-dessus de HI il appartient au dessin. Réglés pour garder la
# lueur verte sans traîner de résidu gris autour.
LO, HI = 34.0, 70.0


def cutout() -> Image.Image:
    """Logo à fond transparent, recadré sur le dessin."""
    src = Image.open(SOURCE).convert('RGB')
    a = np.asarray(src).astype(np.float32)
    bg = np.asarray(src.filter(ImageFilter.GaussianBlur(170))).astype(np.float32)

    distance = np.sqrt(((a - bg) ** 2).sum(axis=2))
    darker = np.clip(bg.mean(axis=2) - a.mean(axis=2), 0, None)
    score = np.maximum(distance, darker)

    alpha = np.clip((score - LO) / (HI - LO), 0, 1)
    alpha = np.asarray(
        Image.fromarray((alpha * 255).astype(np.uint8), 'L')
        .filter(ImageFilter.GaussianBlur(0.8))
    ).astype(np.float32) / 255.0

    a3 = alpha[..., None]
    fg = np.clip(
        np.where(a3 > 0.01, (a - (1 - a3) * bg) / np.maximum(a3, 0.01), 0.0), 0, 255
    )

    out = Image.fromarray(fg.astype(np.uint8), 'RGB')
    out.putalpha(Image.fromarray((alpha * 255).astype(np.uint8), 'L'))

    bbox = Image.fromarray(((alpha * 255) > 30).astype(np.uint8) * 255, 'L').getbbox()
    return out.crop(bbox) if bbox else out


def square(logo: Image.Image, size: int, coverage: float) -> Image.Image:
    """Logo centré dans un carré transparent, occupant `coverage` du côté."""
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    target = size * coverage
    scale = target / max(logo.size)
    art = logo.resize(
        (max(1, round(logo.width * scale)), max(1, round(logo.height * scale))),
        Image.LANCZOS,
    )
    canvas.paste(art, ((size - art.width) // 2, (size - art.height) // 2), art)
    return canvas


def on_background(art: Image.Image, radius_ratio: float | None) -> Image.Image:
    """Pose le logo sur le fond de l'app, éventuellement en tuile arrondie."""
    size = art.width
    plate = Image.new('RGBA', (size, size), (*BG, 255))
    if radius_ratio is not None:
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, size - 1, size - 1), radius=round(size * radius_ratio), fill=255
        )
        plate.putalpha(mask)
    plate.alpha_composite(art)
    return plate


def main() -> int:
    if not SOURCE.exists():
        print(f"❌ Source introuvable : {SOURCE}")
        return 1

    ICONS.mkdir(parents=True, exist_ok=True)
    APP_ASSETS.mkdir(parents=True, exist_ok=True)

    logo = cutout()
    print(f"  ✓ détourage : {logo.size[0]}×{logo.size[1]}")

    # Marque de l'app : transparente, elle doit tenir sur les deux thèmes.
    #
    # 256 px et non 512 : elle s'affiche entre 22 et 88 px, donc 256 couvre
    # déjà les écrans à forte densité. Elle fait partie du shell mis en cache
    # par le service worker, et 512 px coûtait 324 ko pour un gain invisible —
    # sur une connexion mobile, c'est le premier chargement qui le paie.
    square(logo, 256, 0.98).save(APP_ASSETS / 'vizer-logo.png', optimize=True)
    size_kb = (APP_ASSETS / 'vizer-logo.png').stat().st_size // 1024
    print(f"  ✓ src/assets/vizer-logo.png ({size_kb} ko)")

    # Icônes pleines. Le coin arrondi n'est appliqué qu'aux icônes « any » :
    # une maskable est recadrée par le système, elle doit être à fond perdu et
    # garder son dessin dans les 80 % centraux.
    for name, size, coverage, radius in (
        ('icon-192.png', 192, 0.76, 0.22),
        ('icon-512.png', 512, 0.76, 0.22),
        ('apple-touch-icon.png', 180, 0.74, 0.22),
        ('icon.png', 64, 0.84, 0.22),
        ('icon-maskable-512.png', 512, 0.60, None),
    ):
        on_background(square(logo, size, coverage), radius).save(ICONS / name)
        print(f"  ✓ public/icons/{name}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
