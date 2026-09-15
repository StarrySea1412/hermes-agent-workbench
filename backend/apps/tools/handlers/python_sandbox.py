"""受限 Python 沙箱工具：子进程执行短代码片段，回传 stdout/stderr 与产出的图片。

约束（写死在实现里，不给模型调）：
- 独立子进程 + 超时强杀，解释器 -I 隔离启动路径
- 工作目录为沙箱专属临时目录，代码只能写这里
- 不允许 import socket / urllib / requests / http / subprocess / multiprocessing / ctypes / asyncio
- stdout/stderr 截断，防止超长输出撑爆上下文
- 沙箱目录内生成的 .png/.jpg/.svg 会列进 artifacts，文件名由代码自己定
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

MAX_CODE_CHARS = 8000
DEFAULT_TIMEOUT = 20
MAX_TIMEOUT = 60
MAX_OUTPUT_CHARS = 6000
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
ARTIFACT_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg"}

BLOCKED_MODULES = (
    "socket", "urllib", "requests", "http", "ftplib", "telnetlib",
    "subprocess", "multiprocessing", "ctypes", "asyncio", "shutil", "signal",
)
BLOCKED_RE = re.compile(
    r"(?:^|[;\s(])(?:import|from)\s+(" + "|".join(BLOCKED_MODULES) + r")(?:[\s.,;(]|$)",
    re.MULTILINE,
)

META = {
    "source": "builtin",
    "runtime": "sandbox",
    "notes": "Restricted subprocess Python: no network/subprocess modules, temp working dir, hard timeout. Chart images written to the sandbox dir are returned as base64 artifacts.",
}

SCHEMA = {
    "name": "python_sandbox",
    "description": (
        "Execute a short Python snippet in a restricted sandbox to do math, data wrangling, "
        "or render charts. Print final answers to stdout. Charts: matplotlib with Agg backend, "
        "save as .png in the working directory. Network and subprocess modules are blocked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source to execute. Keep it self-contained.",
            },
            "timeout": {
                "type": "integer",
                "description": f"Max seconds to run (1-{MAX_TIMEOUT}). Defaults to {DEFAULT_TIMEOUT}.",
            },
        },
        "required": ["code"],
    },
}


def handle(args, context=None):
    del context

    code = (args.get("code") or "").strip()
    if not code:
        return {"ok": False, "error": "Missing code."}
    if len(code) > MAX_CODE_CHARS:
        return {"ok": False, "error": f"Code exceeds {MAX_CODE_CHARS} characters."}

    blocked = BLOCKED_RE.search(code)
    if blocked:
        return {"ok": False, "error": f"Blocked module import: {blocked.group(1)}. Network/subprocess modules are not available in the sandbox."}

    try:
        timeout = int(args.get("timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    timeout = max(1, min(timeout, MAX_TIMEOUT))

    sandbox_root = os.path.join(tempfile.gettempdir(), "ai-skill-sandbox")
    os.makedirs(sandbox_root, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix="run-", dir=sandbox_root)
    started = time.monotonic()
    try:
        process = subprocess.run(
            [sys.executable, "-I", "-c", code],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
        timed_out = False
        returncode = process.returncode
        stdout = (process.stdout or "")[:MAX_OUTPUT_CHARS]
        stderr = (process.stderr or "")[:MAX_OUTPUT_CHARS]
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = (exc.stdout or "")
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        stdout = stdout[:MAX_OUTPUT_CHARS]
        stderr = f"Execution timed out after {timeout}s and was killed."
    finally:
        artifacts = _collect_artifacts(workdir)
        duration_ms = int((time.monotonic() - started) * 1000)
        shutil.rmtree(workdir, ignore_errors=True)

    result = {
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
    }
    if artifacts:
        result["artifacts"] = artifacts
    if timed_out:
        return {"ok": False, "error": stderr, "result": result}
    return {"ok": returncode == 0, "result": result, "error": "" if returncode == 0 else (stderr or f"Exited with code {returncode}")}


def _collect_artifacts(workdir):
    artifacts = []
    try:
        names = sorted(os.listdir(workdir))
    except OSError:
        return artifacts
    for name in names:
        path = os.path.join(workdir, name)
        if not os.path.isfile(path):
            continue
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in ARTIFACT_SUFFIXES:
            continue
        try:
            if os.path.getsize(path) > MAX_ARTIFACT_BYTES:
                continue
            with open(path, "rb") as fh:
                data = base64.b64encode(fh.read()).decode("ascii")
        except OSError:
            continue
        artifacts.append({
            "filename": name,
            "media_type": "image/svg+xml" if suffix == ".svg" else f"image/{suffix.lstrip('.').replace('jpg', 'jpeg')}",
            "data_base64": data,
        })
    return artifacts
