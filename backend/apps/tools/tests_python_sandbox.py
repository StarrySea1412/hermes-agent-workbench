"""python_sandbox 沙箱工具的回归测试：执行、阻断、超时、产物收集。"""
import base64
import os
import sys
import subprocess
import tempfile
from pathlib import Path
from unittest import mock, skipUnless

from django.test import SimpleTestCase

from apps.tools import registry, schemas
from apps.tools.handlers import python_sandbox
from apps.tools.handlers.python_sandbox import handle


class SandboxExecutionTests(SimpleTestCase):
    def test_prints_to_stdout(self):
        result = handle({"code": "print(sum(range(10)))"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"].strip(), "45")
        self.assertEqual(result["result"]["returncode"], 0)

    def test_runtime_error_surfaces_stderr(self):
        result = handle({"code": "raise ValueError('boom')"})
        self.assertFalse(result["ok"])
        self.assertIn("boom", result["error"])

    def test_missing_code(self):
        self.assertFalse(handle({})["ok"])

    def test_timeout_kills_process(self):
        result = handle({"code": "import time\ntime.sleep(30)", "timeout": 1})
        self.assertFalse(result["ok"])
        self.assertTrue(result["result"]["timed_out"])

    def test_artifact_png_is_collected_as_base64(self):
        code = (
            "import struct, zlib\n"
            "def chunk(tag, data):\n"
            "    c = tag + data\n"
            "    return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c))\n"
            "ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)\n"
            "raw = zlib.compress(b'\\x00\\xff\\x00\\x00')\n"
            "png = b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', raw) + chunk(b'IEND', b'')\n"
            "open('plot.png', 'wb').write(png)\n"
            "print('saved')"
        )
        result = handle({"code": code})
        self.assertTrue(result["ok"], result.get("error"))
        artifacts = result["result"].get("artifacts") or []
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["filename"], "plot.png")
        self.assertEqual(artifacts[0]["media_type"], "image/png")
        # base64 能解回 PNG 魔数，证明内容没损坏
        self.assertTrue(base64.b64decode(artifacts[0]["data_base64"]).startswith(b"\x89PNG"))


class SandboxGuardTests(SimpleTestCase):
    def test_network_modules_blocked(self):
        for code in ["import socket", "import urllib.request", "from http import client", "x=1; import requests"]:
            with self.subTest(code=code):
                result = handle({"code": code})
                self.assertFalse(result["ok"])
                self.assertIn("Blocked module", result["error"])

    def test_subprocess_and_ctypes_blocked(self):
        for code in ["import subprocess", "import ctypes", "from multiprocessing import Process", "import asyncio"]:
            with self.subTest(code=code):
                self.assertFalse(handle({"code": code})["ok"])

    def test_normal_stdlib_allowed(self):
        result = handle({"code": "import json, math, statistics, time\nprint(math.floor(statistics.mean([1,2,3])))"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"].strip(), "2")

    def test_code_size_limit(self):
        result = handle({"code": "x = 1\n" + "# pad\n" * 3000})
        self.assertFalse(result["ok"])
        self.assertIn("exceeds", result["error"])

    def test_relative_file_is_available_during_execution(self):
        result = handle({"code": "import os\nopen('note.txt','w').write('hi')\nprint(os.path.isfile('note.txt'))"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"].strip(), "True")


class SandboxResourceTests(SimpleTestCase):
    def test_output_is_bounded_while_draining(self):
        result = handle({"code": "print('x' * 2000000)"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["result"]["stdout"]), python_sandbox.MAX_OUTPUT_CHARS)

    def test_parent_secrets_are_not_inherited(self):
        with mock.patch.dict(os.environ, {"APP_TEST_SECRET": "not-for-tools"}):
            result = handle({"code": "import os; print(os.getenv('APP_TEST_SECRET', 'absent'))"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["stdout"].strip(), "absent")

    @skipUnless(os.name == 'nt', 'Windows Job Objects')
    def test_memory_allocation_over_job_limit_fails(self):
        result = handle({"code": "data = bytearray(600 * 1024 * 1024); print('allocated')"})
        self.assertFalse(result["ok"], result)
        self.assertIn("MemoryError", result["result"]["stderr"])

    @skipUnless(os.name == 'nt', 'Windows Job Objects')
    def test_job_setup_failure_does_not_run_code(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'should-not-exist'
            with mock.patch('services.windows_job.WindowsJob.attach', side_effect=OSError('denied')):
                result = handle({"code": f"open({str(marker)!r}, 'w').write('executed')"})
            self.assertFalse(result['ok'])
            self.assertFalse(marker.exists())

    @skipUnless(os.name == 'nt', 'Windows Job Objects')
    def test_closing_job_terminates_descendant(self):
        from services.windows_job import WindowsJob

        job = WindowsJob(python_sandbox.MAX_SANDBOX_MEM_BYTES)
        process = subprocess.Popen(
            [sys.executable, '-I', '-u', '-c', 'import sys; exec(sys.stdin.read())'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        child_handle = None
        try:
            job.attach(process)
            code = (
                'import subprocess, sys, time\n'
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],"
                " stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                'print(child.pid, flush=True)\n'
            )
            output, error = process.communicate(code, timeout=5)
            self.assertEqual(process.returncode, 0, error)
            # The child inherits the parent's pipes, so use DEVNULL below for a bounded wait.
            child_pid = int(output.strip())
            import ctypes
            from ctypes import wintypes
            api = job.api
            api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            api.OpenProcess.restype = wintypes.HANDLE
            api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            api.WaitForSingleObject.restype = wintypes.DWORD
            child_handle = api.OpenProcess(0x00100000, False, child_pid)
            self.assertTrue(child_handle)
            job.close()
            self.assertEqual(api.WaitForSingleObject(child_handle, 5000), 0)
        finally:
            job.close()
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
            if child_handle:
                job.api.CloseHandle(child_handle)


class SandboxRegistrationTests(SimpleTestCase):
    def test_registered_in_registry_and_schemas(self):
        self.assertIn("python_sandbox", registry.list_tool_names())
        self.assertIn("python_sandbox", schemas.available_tool_names())
        descriptor = next(d for d in schemas.TOOL_DESCRIPTORS if d["schema"]["name"] == "python_sandbox")
        self.assertIn("code", descriptor["schema"]["parameters"]["properties"])

    def test_registry_execute_roundtrip(self):
        result = registry.execute_tool("python_sandbox", {"code": "print(2**10)"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"].strip(), "1024")
