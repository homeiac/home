"""CPU face detection/embeddings; recognizers return suggestions, never identity facts."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
import uuid

from .metadata import oriented_image

MODELS = {
    "yunet": ("face_detection_yunet", "face_detection_yunet_2023mar.onnx", "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "sface": ("face_recognition_sface", "face_recognition_sface_2021dec.onnx", "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}
MODEL_ID = "yunet-2023mar+sface-2021dec"


def model_file(root: Path, kind: str) -> Path:
    """Require the documented model bytes, not merely a matching filename."""
    _, filename, expected = MODELS[kind]
    path = root / filename
    if not path.is_file():
        raise ValueError("Face model missing; run the models command first")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Face model checksum mismatch: " + filename)
    return path


def download_models(root: Path) -> None:
    """Download official OpenCV artifacts and verify immutable SHA-256 identities."""
    root.mkdir(parents=True, exist_ok=True)
    for kind, (folder, filename, expected) in MODELS.items():
        target = root / filename
        if target.exists():
            model_file(root, kind)
            continue
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/{folder}/{filename}"
        temporary = target.with_suffix(".download")
        try:
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise ValueError("Downloaded model checksum mismatch")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


class FaceEngine:
    def __init__(self, models: Path):
        import cv2
        self.cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(str(model_file(models, "yunet")), "", (320, 320),
                                                 0.85, 0.3, 5000, cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)
        self.recognizer = cv2.FaceRecognizerSF.create(str(model_file(models, "sface")), "",
                                                     cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)

    def detect(self, path: Path) -> list[dict]:
        """Locate and encode faces on oriented, bounded-size pixels."""
        import numpy as np
        image = oriented_image(path)
        image.thumbnail((1600, 1600))
        frame = self.cv2.cvtColor(np.asarray(image), self.cv2.COLOR_RGB2BGR)
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, detected = self.detector.detect(frame)
        results = []
        for face in ([] if detected is None else detected):
            aligned = self.recognizer.alignCrop(frame, face)
            vector = self.recognizer.feature(aligned).reshape(-1)
            vector = vector / max(float(np.linalg.norm(vector)), 1e-12)
            x, y, w, h = map(float, face[:4])
            results.append(dict(id=uuid.uuid4().hex, box=[max(0, x/width), max(0, y/height),
                                                        min(1, (x+w)/width), min(1, (y+h)/height)],
                                confidence=float(face[-1]), embedding=vector.tolist(), model=MODEL_ID))
        return results


def similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity is a ranking score, not a probability."""
    import math
    if not left or len(left) != len(right):
        return -1.0
    denominator = math.sqrt(sum(x*x for x in left) * sum(x*x for x in right))
    return sum(a*b for a, b in zip(left, right)) / denominator if denominator else -1.0


def frigate_candidate(jpeg: bytes) -> dict:
    """Ask the existing recognizer for a candidate; auth stays in environment only."""
    url = os.environ.get("PHOTO_FRIGATE_URL", "").rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Set PHOTO_FRIGATE_URL to the internal Frigate endpoint")
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="face.jpg"\r\n'
            'Content-Type: image/jpeg\r\n\r\n').encode() + jpeg + f'\r\n--{boundary}--\r\n'.encode()
    headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
    token = os.environ.get("PHOTO_FRIGATE_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url + "/api/faces/recognize", body, headers)
    # Do not follow redirects carrying a private face image or authentication header.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        result = json.load(exc)
        # Frigate 0.16 uses HTTP 400 for valid negative recognition results too.
        if result.get("success") is not False or result.get("message") not in (
                "No face was detected.", "No face was recognized."):
            raise
    name = result.get("face_name") if result.get("success") else None
    reason = {"No face was detected.": "no_face", "No face was recognized.": "no_match"}.get(result.get("message"))
    if name == "unknown":
        name = None  # This is Frigate's below-threshold sentinel, not a person name.
        reason = "below_threshold"
    return {"name": name,
            "score": result.get("score"), "source": "frigate", "confirmed": False, "reason": reason}
