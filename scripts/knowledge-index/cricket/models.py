"""Reuse existing local vision endpoints without changing their server configuration."""

import json
import shlex
import subprocess
import urllib.request
from pathlib import Path


def request_body(backend: dict, prompt: str, frames: list[str]) -> tuple[str, dict]:
    """Build the same native Ollama or OpenAI-compatible request used by captions."""
    if backend["api"] == "ollama":
        return "/api/chat", {
            "model": backend["model"],
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "format": "json",
            "options": {"num_ctx": 8192, "num_predict": 1400, "temperature": 0.1},
            "messages": [{"role": "user", "content": prompt, "images": frames}],
        }
    return "/v1/chat/completions", {
        "model": backend["model"],
        "temperature": 0.1,
        "max_tokens": 1400,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    *[
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + frame},
                        }
                        for frame in frames
                    ],
                ],
            }
        ],
    }


REMOTE = r"""
import json,sys,urllib.request
packet=json.load(sys.stdin)
request=urllib.request.Request(packet['url'],json.dumps(packet['body']).encode(),{'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=600) as response:sys.stdout.write(response.read().decode())
"""


def infer(backend: dict, prompt: str, frames: list[str]) -> str:
    """Perform one bounded request; only the local process reads any credential file."""
    route, body = request_body(backend, prompt, frames)
    url = backend["endpoint"].rstrip("/") + route
    transport = backend.get("transport", "http")
    if transport == "ssh":
        response = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                backend["host"],
                "python3 -c " + shlex.quote(REMOTE),
            ],
            input=json.dumps({"url": url, "body": body}),
            capture_output=True,
            text=True,
            timeout=640,
            check=False,
        )
        if response.returncode:
            raise RuntimeError("Remote inference failed")
        value = json.loads(response.stdout)
    elif transport == "qga":
        command = (
            "qm guest exec 108 --timeout 620 --pass-stdin 1 -- curl -fsS --max-time 600 -H "
            + shlex.quote("Content-Type: application/json")
            + " --data-binary @- "
            + shlex.quote(url)
        )
        response = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                backend["host"],
                command,
            ],
            input=json.dumps(body),
            capture_output=True,
            text=True,
            timeout=650,
            check=False,
        )
        if response.returncode:
            raise RuntimeError("Guest inference failed")
        report = json.loads(response.stdout)
        if (
            report.get("exitcode")
            or not report.get("exited")
            or report.get("out-truncated")
        ):
            raise RuntimeError("Guest response incomplete")
        value = json.loads(report["out-data"])
    elif transport == "http":
        headers = {"Content-Type": "application/json"}
        if backend.get("key_file"):
            headers["Authorization"] = (
                "Bearer " + Path(backend["key_file"]).read_text().strip()
            )
        request = urllib.request.Request(url, json.dumps(body).encode(), headers)
        with urllib.request.urlopen(request, timeout=600) as response:
            value = json.load(response)
    else:
        raise ValueError("Unknown inference transport")
    return (
        value["message"]["content"]
        if backend["api"] == "ollama"
        else value["choices"][0]["message"]["content"]
    )
