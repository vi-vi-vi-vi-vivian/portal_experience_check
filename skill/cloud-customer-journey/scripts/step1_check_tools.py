#!/usr/bin/env python3
"""Check runtime dependencies for the cloud-customer-journey skill."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys


def check_module(name: str) -> bool:
    ok = importlib.util.find_spec(name) is not None
    print(f"{'[OK]' if ok else '[MISSING]'} python module: {name}")
    return ok


def check_cmd(name: str, required: bool = False) -> bool:
    path = shutil.which(name)
    if not path:
        print(f"{'[MISSING]' if required else '[OPTIONAL]'} command: {name}")
        return not required
    print(f"[OK] command: {name} -> {path}")
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
        version = (result.stdout or result.stderr).strip().splitlines()
        if version:
            print(f"     {version[0][:160]}")
    except Exception as exc:
        print(f"     version check skipped: {exc}")
    return True


def main() -> int:
    ok = True
    print(f"Python: {sys.version.split()[0]}")
    ok &= sys.version_info >= (3, 9)
    ok &= check_module("requests")
    ok &= check_module("PIL")
    ok &= check_module("playwright")

    if os.environ.get("GEMINI_API_KEY"):
        print("[OK] GEMINI_API_KEY is set")
    else:
        print("[MISSING] GEMINI_API_KEY is not set")
        ok = False

    config_path = os.environ.get("AUDIT_MODEL_CONFIG", "../shared/model_providers.json")
    print(f"Model provider config: {config_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
