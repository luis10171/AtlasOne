"""Check publishable paths and common credential patterns without printing secrets.

This small repository-specific guard complements GitHub secret scanning. It is
not an exhaustive secret detector and does not inspect deleted Git history.
"""

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {".idea", ".vscode", "__pycache__", "media", "transcripts", ".local"}
PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tracked", action="store_true", help="Inspect tracked files only (for CI)."
    )
    args = parser.parse_args()
    command = ["git", "ls-files", "-z"]
    if not args.tracked:
        command.extend(["--cached", "--others", "--exclude-standard"])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=True)
    failures = []
    paths = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
    for filename in paths:
        path = Path(filename)
        private = (
            bool(set(path.parts) & PRIVATE_PARTS)
            or any(part.startswith(".venv") for part in path.parts)
            or (path.name.startswith(".env") and path.name != ".env.example")
            or path.suffix in {".db", ".sqlite3", ".pem", ".key"}
            or ".sqlite3-" in path.name
        )
        if private:
            failures.append(f"{filename}: private or generated file must not be published")
            continue
        candidate = ROOT / path
        if not candidate.exists() or candidate.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            continue
        content = candidate.read_text(encoding="utf-8", errors="replace")
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                failures.append(f"{filename}: possible {label}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"Publication check passed for {len(paths)} files. No listed private paths or credential patterns found."
    )


if __name__ == "__main__":
    main()
