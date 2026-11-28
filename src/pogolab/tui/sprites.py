"""Lossless pixel-art sprite loader and PIL renderer for the TUI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image as PILImage

from pogolab.data.loader import DEFAULT_DATA_DIR


@dataclass(frozen=True, slots=True)
class SpriteData:
    """Palette-indexed pixel sprite cropped tightly to its non-transparent bounds."""

    palette: dict[str, str]
    grid: tuple[str, ...]

    @property
    def width(self) -> int:
        return len(self.grid[0]) if self.grid else 0

    @property
    def height(self) -> int:
        return len(self.grid)


@lru_cache(maxsize=4)
def load_sprites(path: Path | None = None) -> dict[str, SpriteData]:
    """Load species pixel sprites from ``data/sprites.json``.

    Returns an empty mapping if the sprite file is not present.
    """
    sprite_path = path or (DEFAULT_DATA_DIR / "sprites.json")
    if not sprite_path.is_file():
        return {}

    with sprite_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    sprites: dict[str, SpriteData] = {}
    for species_id, entry in raw.items():
        sprites[species_id] = SpriteData(
            palette=dict(entry["p"]),
            grid=tuple(entry["g"]),
        )
    return sprites


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def _hex_to_grayscale(color: str) -> str:
    """Convert a ``#rrggbb`` color to a dimmed grayscale hex string (for fainted sprites)."""
    r, g, b = _hex_to_rgb(color)
    lum = int((0.299 * r + 0.587 * g + 0.114 * b) * 0.55)
    return f"#{lum:02x}{lum:02x}{lum:02x}"


def sprite_to_pil(
    sprite: SpriteData,
    *,
    flip_x: bool = False,
    fainted: bool = False,
    scale: int = 3,
    square_pad: bool = True,
) -> PILImage.Image:
    """Convert a ``SpriteData`` to a crisp RGBA ``PIL.Image`` (lossless pixel art).

    When ``square_pad`` is True, centers the sprite inside a transparent square
    canvas of ``max(width, height)`` so narrow or wide sprites keep their true
    aspect ratio inside square/fixed widget slots. Integer nearest-neighbor
    ``scale`` keeps pixel edges sharp under Sixel / Kitty / iTerm2 rendering.
    """
    src_w = sprite.width
    src_h = sprite.height
    if src_w == 0 or src_h == 0:
        return PILImage.new("RGBA", (1, 1), (0, 0, 0, 0))

    palette = sprite.palette
    if fainted:
        palette = {k: _hex_to_grayscale(v) for k, v in palette.items()}
    rgba_map = {k: (*_hex_to_rgb(v), 255) for k, v in palette.items()}

    img = PILImage.new("RGBA", (src_w, src_h), (0, 0, 0, 0))
    pixels: list[tuple[int, int, int, int]] = []
    for row in sprite.grid:
        iterable = reversed(row) if flip_x else row
        for ch in iterable:
            pixels.append((0, 0, 0, 0) if ch == "." else rgba_map.get(ch, (0, 0, 0, 0)))
    img.putdata(pixels)

    if square_pad and src_w != src_h:
        side = max(src_w, src_h)
        canvas = PILImage.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - src_w) // 2, (side - src_h) // 2))
        img = canvas

    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), PILImage.Resampling.NEAREST)
    return img
