"""Trusted-code Python runner with time/output limits and Windows job limits.

The temporary working directory and import checks are not filesystem or network
isolation. Do not expose this runner to untrusted users or untrusted code.
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

MAX_CODE_CHARS = 8000
DEFAULT_TIMEOUT = 20
MAX_TIMEOUT = 60
MAX_OUTPUT_CHARS = 6000
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_SANDBOX_MEM_BYTES = 512 * 1024 * 1024
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
    "notes": "Trusted-code runner: timeout, bounded output, and Windows job memory/process-tree limits. Not filesystem or network isolation.",
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
    should_cancel = (context or {}).get("should_cancel")

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
    process = None
    job = None
    readers = []
    outputs = [bytearray(), bytearray()]
    timed_out = False
    artifacts = []
    try:
        if os.name == "nt":
            from services.windows_job import WindowsJob

            job = WindowsJob(MAX_SANDBOX_MEM_BYTES)
        # User code is delivered only after the process has joined the job.
        bootstrap = "import sys; exec(compile(sys.stdin.buffer.read().decode('utf-8'), '<tool>', 'exec'))"
        env = {key: value for key, value in os.environ.items()
               if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}
        env.update({"MPLCONFIGDIR": workdir, "HOME": workdir, "USERPROFILE": workdir})
        process = subprocess.Popen(
            [sys.executable, "-I", "-u", "-c", bootstrap],
            cwd=workdir, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
        if job:
            job.attach(process)
        for pipe, output in zip((process.stdout, process.stderr), outputs):
            reader = threading.Thread(target=_drain_output, args=(pipe, output), daemon=True)
            reader.start()
            readers.append(reader)
        process.stdin.write(code.encode("utf-8"))
        process.stdin.close()
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if should_cancel and should_cancel():
                return {"ok": False, "error": "Execution cancelled."}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                process.wait(timeout=min(0.1, remaining))
            except subprocess.TimeoutExpired:
                pass
        _terminate_job(process, job)
        for reader in readers:
            reader.join(timeout=5)
        returncode = process.returncode if process.returncode is not None else -1
        stdout, stderr = [bytes(output).decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS]
                          for output in outputs]
        if timed_out:
            stderr = f"Execution timed out after {timeout}s and was killed."
        artifacts = _collect_artifacts(workdir)
    except Exception as exc:
        return {"ok": False, "error": f"Python runner could not execute: {exc}"}
    finally:
        _terminate_job(process, job)
        for reader in readers:
            reader.join(timeout=5)
        if process:
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
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


def _drain_output(pipe, output):
    try:
        while True:
            block = pipe.read(4096)
            if not block:
                break
            remaining = MAX_OUTPUT_CHARS * 4 - len(output)
            if remaining > 0:
                output.extend(block[:remaining])
    except (OSError, ValueError):
        pass


def _terminate_job(process, job):
    if job:
        job.close()
    elif process and os.name != "nt":
        import signal

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process and process.poll() is None:
        process.kill()
        process.wait(timeout=5)


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
