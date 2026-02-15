#!/usr/bin/env python3
"""
CodeAlive Auth Check — verify API key is configured (no network requests).

Exit codes:
    0 — API key found and ready
    1 — API key not found, setup required
"""

import os
import sys
import platform
import subprocess

SERVICE_NAME = "codealive-api-key"


def find_key() -> bool:
    """Check if an API key exists in env var or OS credential store."""
    if os.getenv("CODEALIVE_API_KEY"):
        return True

    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(
                ["security", "find-generic-password", "-a", os.getenv("USER", ""), "-s", SERVICE_NAME, "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return True
        elif system == "Linux":
            r = subprocess.run(
                ["secret-tool", "lookup", "service", SERVICE_NAME],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return True
    except (FileNotFoundError, Exception):
        pass

    return False


def main():
    if find_key():
        print("CodeAlive API key found. Ready to use.")
        sys.exit(0)
    else:
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        setup_path = os.path.join(skill_dir, "setup.py")
        print(
            "CodeAlive API key not configured.\n"
            "\n"
            "Run the interactive setup:\n"
            f"  python {setup_path}\n"
            "\n"
            "Or set the key manually:\n"
            "  export CODEALIVE_API_KEY=\"your_key\"\n"
            "\n"
            "Get your API key at: https://app.codealive.ai/settings/api-keys"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
