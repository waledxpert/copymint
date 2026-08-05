"""Small fail-closed repository secret scanner used in local checks and CI."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "htmlcov",
}
TEXT_SUFFIXES = {
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sql",
    ".toml",
    ".yaml",
    ".yml",
}
PATTERNS = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "chainstack_endpoint_credential": re.compile(
        r"https?://[^\s]+\.chainstack\.com/[A-Fa-f0-9]{24,}"
    ),
    "pem_private_key": re.compile(r"-----BEGIN (?:EC |RSA )?PRIVATE KEY-----"),
    "telegram_bot_token": re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),
    "labeled_evm_private_key": re.compile(
        r"(?i)(?:private[_ -]?key|secret[_ -]?key)\s*[:=]\s*0x[A-Fa-f0-9]{64}\b"
    ),
}


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        if path.name == ".env.example" or path.suffix.casefold() in TEXT_SUFFIXES:
            files.append(path)
    return files


def main() -> int:
    findings: list[str] = []
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "secret-scan: allow-test-fixture" in line:
                continue
            for name, pattern in PATTERNS.items():
                match = pattern.search(line)
                if match and "replace" not in match.group(0).casefold():
                    relative = path.relative_to(ROOT)
                    findings.append(f"{relative}:{line_number}: possible {name}")
    if findings:
        print("Secret scan failed:")
        print("\n".join(findings))
        return 1
    print(f"Secret scan passed ({len(iter_text_files())} text files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
