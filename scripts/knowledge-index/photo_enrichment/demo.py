"""Create an artificial local preview library, never a copy of private user photos."""
import datetime as dt
import json
from pathlib import Path

from PIL import Image, ImageDraw


def build_demo(root: Path) -> tuple[Path, Path]:
    from adapters.gphotos import emit
    from kidx import rebuild
    library, index = root / "library", root / "index"
    folder = library / "Google Photos" / "Photos from 2023"
    folder.mkdir(parents=True, exist_ok=True)
    palettes = [("#bdd7cd", "#426e5d"), ("#e2bfaa", "#926754"), ("#bdccd9", "#47677b"), ("#dbcfa8", "#807841")]
    for n in range(8):
        name = f"demo-{n+1:02}.jpg"
        image = Image.new("RGB", (700, 500), palettes[n % 4][0])
        draw = ImageDraw.Draw(image)
        draw.polygon([(0, 500), (240, 150+n*10), (430, 390), (590, 210), (700, 500)], fill=palettes[n % 4][1])
        draw.ellipse((500, 35, 580, 115), fill="#fff5d8")
        draw.text((28, 30), f"DEMO IMAGE {n+1:02} - synthetic fixture", fill="#233e35")
        exif = Image.Exif()
        exif[271] = "Demo camera"
        exif[272] = "Test fixture"
        exif[306] = "2023:04:23 14:30:00"
        image.save(folder / name, exif=exif)
        date = dt.datetime(2023, 4, 23 if n < 6 else 24, 15+n%6, tzinfo=dt.timezone.utc)
        meta = {"title": name, "creationTime": {"timestamp": str(int(date.timestamp()))}, "photoTakenTime": {"timestamp": str(int(date.timestamp()))},
                "geoData": {"latitude": 0, "longitude": 0}, "people": []}
        (folder / (name + ".json")).write_text(json.dumps(meta))
    emit("demo", str(library), str(index))
    rebuild(str(index))
    return index, library


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.directory.exists():
        parser.error("Use a new empty demo directory")
    build_demo(args.directory)
