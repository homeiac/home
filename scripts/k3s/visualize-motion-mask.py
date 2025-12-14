#!/usr/bin/env python3
"""Visualize current motion mask to see what's covered vs exposed."""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw

# Current motion mask from Frigate config
MOTION_MASK = "0.003,0.004,1,0,1,0.395,0.878,0.421,0.813,0.429,0.557,0.429,0.426,0.337,0.432,0.409,0.123,0.491,0.177,1,0,1"

def parse_coords(coord_str):
    coords = [float(c) for c in coord_str.split(",")]
    return [(coords[i], coords[i+1]) for i in range(0, len(coords), 2)]

def main():
    script_dir = Path(__file__).parent
    analysis_dir = script_dir / "doorbell-analysis"

    snapshots = sorted(analysis_dir.glob("snapshot-*.jpg"))
    if not snapshots:
        print("No snapshots found")
        return

    input_path = snapshots[-1]
    img = Image.open(input_path)
    width, height = img.size

    # Parse mask
    mask_points = parse_coords(MOTION_MASK)
    scaled_points = [(int(x * width), int(y * height)) for x, y in mask_points]

    print(f"Motion mask has {len(mask_points)} points")

    # Create overlay
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw masked area in red (motion IGNORED here)
    draw.polygon(scaled_points, fill=(255, 0, 0, 120), outline=(255, 0, 0, 255))

    # Composite
    img_rgba = img.convert('RGBA')
    result = Image.alpha_composite(img_rgba, overlay)

    # Add header
    final = Image.new('RGB', (width, height + 50), (30, 30, 30))
    final.paste(result.convert('RGB'), (0, 50))
    draw_final = ImageDraw.Draw(final)
    draw_final.text((20, 15), "RED = Motion MASKED (ignored) | CLEAR = Motion ACTIVE (triggers detection)", fill=(255, 255, 255))

    output_path = analysis_dir / "motion-mask-current.jpg"
    final.save(output_path, quality=90)
    print(f"Output: {output_path}")

if __name__ == "__main__":
    main()
