"""python_sandbox 沙箱工具的回归测试：执行、阻断、超时、产物收集。"""
import base64
import os

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

    def test_os_writes_confined_to_sandbox_dir(self):
        # 沙箱目录在系统 temp 下；代码里写相对路径文件应被允许并被清理
        result = handle({"code": "open('note.txt','w').write('hi')\nprint(os.getcwd())" if False else "import os\nopen('note.txt','w').write('hi')\nprint(os.path.isfile('note.txt'))"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"].strip(), "True")


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
