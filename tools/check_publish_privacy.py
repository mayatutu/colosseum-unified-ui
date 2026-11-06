"""Reject environment details in tracked files and reachable Git history.

Print locations and categories only. Never echo the matched sensitive values.
"""
import argparse
import hashlib
import ipaddress
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
RULES = {
    "machine-home-path": re.compile(r"/(?:home|Users)/[^\s/\"'`]+/"),
    "machine-windows-path": re.compile(r"\b[A-Z]:[/\\](?:Users|working|Program Files)[/\\]", re.I),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "access-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{25,}|github_pat_[A-Za-z0-9_]{25,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,})\b"),
    "real-evaluation-id": re.compile(r"\b(?:ev|run)_[a-f0-9]{24,}\b"),
}
PRIVATE_PARTS = {"data", "eval_runs", "eval_review_cache", "agent-logs", "browser-profile"}
PRIVATE_SUFFIXES = {".png", ".jpg", ".jpeg", ".log", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx", ".zip", ".gz"}
SYNTHETIC_MEDIA = {
    "validation/feedback-test-video.mp4": "10e74f65aa6954c90afb5e7aa406e6ee22e407c12ac74bc506f935ca7a24d8e2",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def text_issues(data):
    text = data.decode("utf-8", errors="replace")
    problems = {name for name, pattern in RULES.items() if pattern.search(text)}
    for match in IPV4.finditer(text):
        try:
            address = ipaddress.ip_address(match.group())
        except ValueError:
            continue
        if not (address.is_loopback or address.is_unspecified):
            problems.add("non-loopback-ip-address")
    for match in EMAIL.finditer(text):
        domain = match.group(1).lower()
        if domain != "users.noreply.github.com" and not domain.endswith(".invalid"):
            problems.add("personal-email")
    return problems


def file_issues(name, data):
    path = Path(name)
    if name in SYNTHETIC_MEDIA:
        return set() if hashlib.sha256(data).hexdigest() == SYNTHETIC_MEDIA[name] else {"unreviewed-media"}
    problems = text_issues(data)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        problems.add("unreviewed-binary")
    if set(path.parts) & PRIVATE_PARTS or path.suffix.lower() in PRIVATE_SUFFIXES:
        problems.add("private-artifact")
    if path.name.startswith(".env") or path.name.endswith((".local.yaml", ".local.yml")):
        problems.add("private-config")
    if path.parts[0] == "validation" and path.suffix in (".json", ".xml"):
        problems.add("generated-report")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also inspect all reachable commits and their file trees")
    args = parser.parse_args()
    failures = set()
    seen = set()

    def inspect(name, data, location):
        key = (name, hashlib.sha256(data).digest())
        if key in seen:
            return
        seen.add(key)
        for problem in file_issues(name, data):
            failures.add((location + ":" + name, problem))

    names = git("ls-files", "-z").decode().rstrip("\0").split("\0")
    for name in filter(None, names):
        path = ROOT / name
        if path.is_file():
            inspect(name, path.read_bytes(), "working-tree")
        try:
            data = git("show", ":" + name)
        except subprocess.CalledProcessError:
            continue
        inspect(name, data, "index")
    if args.history:
        for commit in git("rev-list", "--all").decode().splitlines():
            metadata = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", commit)
            for problem in text_issues(metadata):
                failures.add(("commit:" + commit[:12], problem))
            entries = git("ls-tree", "-r", "-z", commit).decode().rstrip("\0").split("\0")
            for entry in filter(None, entries):
                meta, name = entry.split("\t", 1)
                _, kind, object_id = meta.split()
                if kind == "blob":
                    inspect(name, git("cat-file", "blob", object_id), "history")
    for location, problem in sorted(failures):
        print(f"{location}: {problem}")
    if failures:
        print(f"Privacy check failed: {len(failures)} finding(s); matched values omitted.")
        return 1
    print(f"Privacy check passed: {len(seen)} file version(s) checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
