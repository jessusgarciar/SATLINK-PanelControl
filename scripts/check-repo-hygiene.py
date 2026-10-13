"""Reject private files and recognizable secrets in Git's index. Never print secret values."""
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


private_names = {"env", ".envrc", "mission.local.json", "prediction-settings.local.json"}
private_dirs = {".local", ".venv", "node_modules", "__pycache__", ".pytest_cache", "logs"}
secret_patterns = [
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    rb"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}\b",
    rb"\bAKIA[0-9A-Z]{16}\b",
    rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b",
]
failures = []
files = [p.decode("utf-8") for p in git("ls-files", "-z").split(b"\0") if p]
worktree = "--worktree" in sys.argv[1:]
if worktree:
    files = sorted(set(files) | {p.decode("utf-8") for p in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if p})
    files = [p for p in files if Path(p).is_file()]
for filename in files:
    p = PurePosixPath(filename)
    example = p.name.startswith(".env") and p.name.endswith(".example")
    if ((p.name.startswith(".env") and not example) or p.name in private_names
            or set(p.parts) & private_dirs or p.suffix.lower() in {".pem", ".key", ".pfx", ".p12", ".dump", ".backup"}):
        failures.append(f"{filename}: archivo privado en el índice")
        continue
    content = Path(filename).read_bytes() if worktree else git("show", ":" + filename)
    if any(re.search(pattern, content) for pattern in secret_patterns):
        failures.append(f"{filename}: formato reconocible de secreto")
    if example:
        for line in content.decode("utf-8").splitlines():
            match = re.match(r"([A-Z][A-Z0-9_]*)=(.*)", line)
            if not match:
                continue
            key, value = match.groups()
            if re.search(r"PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY", key) and value.strip():
                failures.append(f"{filename}: {key} debe quedar vacío en el ejemplo")
            if re.search(r"://[^\s/@:]+:[^\s/@]+@", value):
                failures.append(f"{filename}: URL con contraseña en el ejemplo")

if failures:
    print("\n".join(failures))
    sys.exit(1)
scope = "árbol de trabajo público" if worktree else "índice"
print(f"OK: {len(files)} archivos del {scope}; sin archivos privados ni formatos de secretos detectados.")
