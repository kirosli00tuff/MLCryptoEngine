"""Generate the app icons (node-net glyph on void background), stdlib only.

Deterministic output: rerunning produces identical PNGs. Usage:
    python3 desktop/src-tauri/icons/gen_icons.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

VOID = (10, 13, 19, 255)
CORTEX = (154, 140, 255, 255)
BID = (45, 212, 167, 255)
INK = (201, 209, 221, 255)
EDGE = (154, 140, 255, 70)

# Node layout in unit coordinates: (x, y, radius_fraction, color)
NODES = [
    (0.50, 0.22, 0.09, CORTEX),
    (0.24, 0.68, 0.09, BID),
    (0.76, 0.68, 0.09, CORTEX),
    (0.50, 0.52, 0.06, INK),
    (0.35, 0.40, 0.045, CORTEX),
    (0.66, 0.42, 0.045, BID),
]
EDGES = [(0, 3), (1, 3), (2, 3), (0, 4), (1, 4), (0, 5), (2, 5), (1, 2)]


def _blend(
    base: tuple[int, int, int, int], top: tuple[int, int, int, int], alpha: float
) -> tuple[int, int, int, int]:
    a = max(0.0, min(1.0, alpha)) * (top[3] / 255)
    return (
        int(base[0] * (1 - a) + top[0] * a),
        int(base[1] * (1 - a) + top[1] * a),
        int(base[2] * (1 - a) + top[2] * a),
        255,
    )


def _render(size: int) -> list[list[tuple[int, int, int, int]]]:
    grid = [[VOID for _ in range(size)] for _ in range(size)]

    # Edges: distance-to-segment antialiased lines.
    edge_width = max(1.0, size / 34)
    for a_idx, b_idx in EDGES:
        ax, ay = NODES[a_idx][0] * size, NODES[a_idx][1] * size
        bx, by = NODES[b_idx][0] * size, NODES[b_idx][1] * size
        min_x = int(max(0, min(ax, bx) - edge_width - 1))
        max_x = int(min(size - 1, max(ax, bx) + edge_width + 1))
        min_y = int(max(0, min(ay, by) - edge_width - 1))
        max_y = int(min(size - 1, max(ay, by) + edge_width + 1))
        seg_len_sq = (bx - ax) ** 2 + (by - ay) ** 2 or 1.0
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                t = max(0.0, min(1.0, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / seg_len_sq))
                dx, dy = x - (ax + t * (bx - ax)), y - (ay + t * (by - ay))
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < edge_width:
                    grid[y][x] = _blend(grid[y][x], EDGE, 1 - dist / edge_width)

    # Nodes: filled antialiased circles.
    for nx, ny, nr, color in NODES:
        cx, cy, radius = nx * size, ny * size, nr * size
        min_x = int(max(0, cx - radius - 2))
        max_x = int(min(size - 1, cx + radius + 2))
        min_y = int(max(0, cy - radius - 2))
        max_y = int(min(size - 1, cy + radius + 2))
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                if dist < radius + 1:
                    grid[y][x] = _blend(grid[y][x], color, min(1.0, radius + 1 - dist))
    return grid


def _write_png(path: Path, grid: list[list[tuple[int, int, int, int]]]) -> None:
    size = len(grid)
    raw = b"".join(b"\x00" + b"".join(struct.pack("4B", *pixel) for pixel in row) for row in grid)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload))
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main() -> None:
    here = Path(__file__).resolve().parent
    for name, size in (("32x32.png", 32), ("128x128.png", 128), ("icon.png", 256)):
        _write_png(here / name, _render(size))
        print(f"wrote {here / name}")


if __name__ == "__main__":
    main()
