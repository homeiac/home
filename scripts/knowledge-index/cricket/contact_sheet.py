"""Show delivery chronology in one timestamped image to avoid isolated-frame responses."""

import base64
import io

from PIL import Image, ImageDraw


def sheet(window: dict) -> str:
    """Combine existing decoded evidence; the original source is never altered."""
    frames = window["frames"]
    if not 1 <= len(frames) <= 8:
        raise ValueError("Expected one to eight evidence frames")
    if len(frames) == 1:
        return frames[0]
    columns = min(4, len(frames))
    rows = (len(frames) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * 384, rows * 284), "white")
    draw = ImageDraw.Draw(canvas)
    for i, frame in enumerate(frames):
        with Image.open(io.BytesIO(base64.b64decode(frame, validate=True))) as image:
            image = image.convert("RGB")
            image.thumbnail((384, 256))
            x = i % columns * 384
            y = i // columns * 284
            canvas.paste(
                image,
                (x + (384 - image.width) // 2, y + 28 + (256 - image.height) // 2),
            )
            draw.text(
                (x + 8, y + 8),
                f"Frame {i + 1} | source {window['positions'][i]:.2f}s",
                fill="black",
            )
    output = io.BytesIO()
    canvas.save(output, "JPEG", quality=88)
    return base64.b64encode(output.getvalue()).decode()
