"""Phase 7: upload this project's CODE to GitHub (branch "main"), so GitHub Actions can run it.

    python upload_code.py            # list what would be uploaded, then ask before uploading
    python upload_code.py --yes      # upload without asking

Uploaded: .py, .bat, .md, .yml, config.json, requirements.txt, .gitignore, .env.example,
public/index.html and the chart library. NEVER uploaded: .env (your keys), .venv, data/
(your archive, news, logs), public/signals.json and public/charts/ (data).
Every file is also checked for your keys before upload; any match stops the upload.
"""
import os
import sys
from pathlib import Path

from sd import env
from sd.env import ROOT
from sd.github import GitHubError, Repo

env.load()

SKIP_DIRS = {".venv", "data", "__pycache__", ".git", "charts"}
SKIP_FILES = {".env", "signals.json"}
ALLOWED = {".py", ".bat", ".md", ".yml", ".yaml", ".json", ".txt", ".html", ".js", ".example", ".gitignore"}


def code_files():
    """Walk the project, never entering skipped folders (.venv alone has thousands of files)."""
    out = {}
    for folder, dirs, names in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            p = Path(folder) / name
            if name in SKIP_FILES or (p.suffix not in ALLOWED and name not in ALLOWED):
                continue
            out[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    return out


def main():
    token, repo = env.get("GITHUB_TOKEN"), env.get("GITHUB_REPO")
    if not token or not repo:
        print("Add GITHUB_TOKEN and GITHUB_REPO to .env first (see README, Phase 7).")
        return 1
    files = code_files()
    for path, content in files.items():
        text = content.decode("utf-8", "ignore")
        for secret in env.secrets() + [env.get("DASHBOARD_PASSPHRASE") or ""]:
            if secret and len(secret) >= 6 and secret in text:
                print(f"STOP: {path} contains one of your keys or the passphrase. Nothing was uploaded.")
                return 1
    print(f"{len(files)} files to upload to {repo} (branch main):")
    for path in files:
        print("  " + path)
    if "--yes" not in sys.argv and input("\nUpload these? (y/n) ").strip().lower() != "y":
        print("Cancelled.")
        return 0
    try:
        sha = Repo(token, repo).put_files("main", files, "Update signal-dashboard code")
    except GitHubError as e:
        print(f"Upload failed: {e}")
        return 1
    print(f"Uploaded ({sha[:7]}): https://github.com/{repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
