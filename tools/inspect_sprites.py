"""Inspect pre-baked fish sprites without starting the desktop application.

Run ``python tools/inspect_sprites.py --output inspect_out.json`` to write the
report. Importing this module only exposes ``inspect`` and never writes files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PySide6.QtGui import QImage

ASSET_DIR = Path(__file__).resolve().parents[1]/"assets"/"fish"
KINDS = ("koi", "goldfish", "neon", "betta")


def _thirds(masses):
    total = sum(masses)
    if not total:
        return [0.0, 0.0, 0.0]
    count = len(masses)
    return [round(sum(masses[i*count//3:(i+1)*count//3])/total, 3)
            for i in range(3)]


def inspect(kind: str, asset_dir=None, sample_count: int = 5) -> dict:
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    directory = Path(asset_dir if asset_dir is not None else ASSET_DIR)/kind
    frames = sorted(path for path in directory.iterdir()
                    if path.is_file() and path.suffix.lower() == ".png")
    samples = frames[:sample_count]
    info = {"kind": kind, "frame_count": len(frames),
            "frames": [path.name for path in frames[:3]],
            "sample_count": len(samples)}
    total_x = total_y = total_alpha = 0
    rows, columns = [], []
    for path in samples:
        image = QImage(str(path)).convertToFormat(QImage.Format_RGBA8888)
        if image.isNull():
            raise ValueError(f"Cannot read sprite: {path}")
        width, height = image.width(), image.height()
        if "size" not in info:
            info["size"] = [width, height]
            rows, columns = [0]*height, [0]*width
        elif info["size"] != [width, height]:
            raise ValueError(f"Sprite dimensions differ within {kind}: {path.name}")
        pixels = image.constBits()
        stride = image.bytesPerLine()
        for y in range(height):
            for x in range(width):
                alpha = pixels[y*stride+x*4+3]
                if alpha > 24:
                    rows[y] += alpha
                    columns[x] += alpha
                    total_y += alpha*y
                    total_x += alpha*x
                    total_alpha += alpha
    if samples:
        # Both the distribution and centroid use all sampled frames, weighted
        # by alpha. total_alpha already includes each frame: no second division.
        info["mass_y_thirds"] = _thirds(rows)
        info["mass_x_thirds"] = _thirds(columns)
    if total_alpha:
        info["mean_center"] = [round(total_x/total_alpha, 1),
                               round(total_y/total_alpha, 1)]
    return info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="inspect_out.json",
                        help="JSON output path (default: inspect_out.json); '-' prints only")
    args = parser.parse_args(argv)
    data = {kind: inspect(kind) for kind in KINDS}
    report = json.dumps(data, indent=1, ensure_ascii=False)
    if args.output != "-":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report+"\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
