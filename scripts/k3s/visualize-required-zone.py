#!/usr/bin/env python3
"""
Visualize proposed required zone for doorbell camera.
Objects detected OUTSIDE this zone will be ignored.
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw

# Exact zone from Frigate config export - zone named "porch"
# top-left, top-right, bottom-right, bottom-left
REQUIRED_ZONE = "0.165,0.481,1,0.398,1,1,0.219,1"

def parse_coords(coord_str):
    coords = [float(c) for c in coord_str.split(",")]
    return [(coords[i], coords[i+1]) for i in range(0, len(coords), 2)]

def main():
    script_dir = Path(__file__).parent
    analysis_dir = script_dir / "doorbell-analysis"

    snapshots = sorted(analysis_dir.glob("snapshot-*.jpg"))
    if not snapshots:
        print("No snapshots found. Run doorbell-motion-analysis.sh first.")
        return

    input_path = snapshots[-1]
    img = Image.open(input_path)
    width, height = img.size

    print(f"Image: {input_path.name} ({width}x{height})")

    # Parse zone coordinates
    zone_points = parse_coords(REQUIRED_ZONE)
    scaled_points = [(int(x * width), int(y * height)) for x, y in zone_points]

    # Create overlay
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Fill entire image with red (ignored area)
    draw.rectangle([(0, 0), (width, height)], fill=(255, 0, 0, 100))

    # Draw zone in green (objects tracked here) - this will overlay the red
    draw.polygon(scaled_points, fill=(0, 200, 100, 150), outline=(0, 255, 0, 255))

    # Composite
    img_rgba = img.convert('RGBA')
    result = Image.alpha_composite(img_rgba, overlay)

    # Add measurement overlays for cars and person
    draw_result = ImageDraw.Draw(result)

    # Distance-to-pixel scaling function (objects appear smaller when farther)
    def meters_to_pixels_at_y(meters, y_coord):
        """Convert real-world meters to pixels at a given y-coordinate."""
        # At y=1.0 (1.2m away), 1 meter ≈ 400 pixels (close up)
        # At y=0.4 (28m away), 1 meter ≈ 15 pixels (far away)
        near_scale = 400  # pixels per meter at y=1.0
        far_scale = 15    # pixels per meter at y=0.4
        far_y = 0.4

        if y_coord >= 1.0:
            return int(meters * near_scale)
        t = (1.0 - y_coord) / (1.0 - far_y)
        scale = near_scale - (near_scale - far_scale) * (t ** 1.2)
        return int(meters * scale)

    # Draw cars at top line (street level, y ≈ 0.42)
    car_y = 0.42
    car_length_m = 4.5
    car_height_m = 1.5
    car_pixel_y = int(car_y * height)
    car_length_px = meters_to_pixels_at_y(car_length_m, car_y)
    car_height_px = meters_to_pixels_at_y(car_height_m, car_y)

    # Draw 3 cars at street level
    car_positions = [0.3, 0.5, 0.75]  # x positions
    for i, car_x in enumerate(car_positions):
        cx = int(car_x * width)
        # Draw car box (yellow)
        car_box = [
            (cx - car_length_px//2, car_pixel_y - car_height_px),
            (cx + car_length_px//2, car_pixel_y)
        ]
        draw_result.rectangle(car_box, outline=(255, 255, 0, 255), width=2)
        # Label with measurement
        label = f"Car {i+1}: 4.5m"
        draw_result.text((car_box[0][0], car_box[0][1] - 15), label, fill=(255, 255, 0, 255))

    # Draw person near pillar (y ≈ 0.7)
    person_y = 0.75
    person_x = 0.45  # near center pillar
    person_height_m = 1.7
    person_width_m = 0.5
    person_pixel_y = int(person_y * height)
    person_height_px = meters_to_pixels_at_y(person_height_m, person_y)
    person_width_px = meters_to_pixels_at_y(person_width_m, person_y)

    px = int(person_x * width)
    person_box = [
        (px - person_width_px//2, person_pixel_y - person_height_px),
        (px + person_width_px//2, person_pixel_y)
    ]
    draw_result.rectangle(person_box, outline=(0, 255, 255, 255), width=2)
    draw_result.text((person_box[0][0], person_box[0][1] - 15), "Person: 1.7m", fill=(0, 255, 255, 255))

    # Add header bar with labels
    final = Image.new('RGB', (width, height + 50), (30, 30, 30))
    final.paste(result.convert('RGB'), (0, 50))
    draw_final = ImageDraw.Draw(final)
    draw_final.text((20, 15), "RED = Ignored | GREEN = Zone | YELLOW = Cars | CYAN = Person", fill=(255, 255, 255))

    output_path = analysis_dir / "required-zone.jpg"
    final.save(output_path, quality=90)

    print(f"Output: {output_path}")
    print(f"\nRequired zone for Frigate config:")
    print(f"  coordinates: {REQUIRED_ZONE}")

    # Calculate distance estimates for each line
    # Based on doorbell camera perspective:
    # - y=0 is far (top of frame)
    # - y=1 is near (bottom of frame, porch)
    # Rough estimate: y=1.0 ~ 1.2m, y=0.4 ~ 11m (street level)

    def y_to_distance_meters(y):
        """Convert y-coordinate to estimated distance in meters.

        Doorbell camera has wide-angle/fisheye lens with skewed perspective.
        Based on visible cars (~4.5m each) and typical residential layout:
        - y=1.0 (porch): ~1.2m
        - y=0.4 (street with parked cars): ~25-30m
        """
        # Exponential relationship due to perspective distortion
        # y=1.0 -> 1.2m, y=0.4 -> 28m
        near_dist = 1.2
        far_dist = 28
        far_y = 0.4

        if y >= 1.0:
            return near_dist
        # Use exponential for perspective distortion
        t = (1.0 - y) / (1.0 - far_y)
        dist = near_dist + (far_dist - near_dist) * (t ** 1.5)
        return round(dist, 1)

    points = zone_points
    num_points = len(points)

    print(f"\n--- Speed Estimation Distances (meters) ---")
    print(f"Zone has {num_points} points, {num_points} lines")
    print()

    lines = []
    for i in range(num_points):
        p1 = points[i]
        p2 = points[(i + 1) % num_points]
        # Average y of the two endpoints
        avg_y = (p1[1] + p2[1]) / 2
        dist = y_to_distance_meters(avg_y)
        line_name = chr(ord('a') + i)
        lines.append(dist)
        print(f"  line_{line_name}: {dist}  # ({p1[0]:.2f},{p1[1]:.2f}) to ({p2[0]:.2f},{p2[1]:.2f}), avg y={avg_y:.2f}")

    print(f"\nFrigate config format:")
    print(f"  distances:")
    for i, dist in enumerate(lines):
        print(f"    - {dist}   # line_{chr(ord('a') + i)}")

if __name__ == "__main__":
    main()
