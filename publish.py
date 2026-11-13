"""Phase 7: publish the dashboard to GitHub Pages, encrypted, so you can open it on your phone.

    python publish.py                 # from your PC (the scanner runs this every 15 minutes)
    python publish.py --source actions  (what GitHub Actions runs)
    python publish.py --preview       # build the site into data/site_preview/ without uploading

What goes online (branch "gh-pages", REPLACED each time so its history never piles up):
  index.html, the chart library, status.json (only the time and source, not encrypted),
  enc/signals.enc and enc/charts/*.enc (encrypted with DASHBOARD_PASSPHRASE).
Never uploaded: your keys (.env), the price archive (data/), your XM balance (it stays in your browser).

Needs in .env:  GITHUB_TOKEN, GITHUB_REPO (e.g. yourname/signal-dashboard), DASHBOARD_PASSPHRASE.
On GitHub Actions, GITHUB_TOKEN and GITHUB_REPOSITORY are provided automatically.
"""
import json
import os
import sys
from datetime import datetime, timezone

from sd import crypto, env, store
from sd.github import GitHubError, Repo

env.load()

PUBLIC = store.ROOT / "public"
BRANCH = "gh-pages"


def settings():
    token = env.get("GITHUB_TOKEN")
    repo = env.get("GITHUB_REPO") or os.environ.get("GITHUB_REPOSITORY")
    passphrase = env.get("DASHBOARD_PASSPHRASE")
    missing = [n for n, v in (("GITHUB_TOKEN", token), ("GITHUB_REPO", repo), ("DASHBOARD_PASSPHRASE", passphrase)) if not v]
    return token, repo, passphrase, missing


def build(repo, passphrase, source):
    """{path: bytes} for the website. Plain data files are never included, only encrypted ones."""
    signals = json.loads((PUBLIC / "signals.json").read_text(encoding="utf-8"))
    salt = crypto.salt_for(repo)
    key = crypto.derive_key(passphrase, salt)
    enc = lambda raw: json.dumps(crypto.encrypt(key, raw), separators=(",", ":")).encode()
    files = {
        "index.html": (PUBLIC / "index.html").read_bytes(),
        "vendor/lightweight-charts.js": (PUBLIC / "vendor" / "lightweight-charts.js").read_bytes(),
        ".nojekyll": b"",                       # serve files as they are (no Jekyll processing)
        "enc/signals.enc": enc((PUBLIC / "signals.json").read_bytes()),
        "status.json": json.dumps({
            "format": 1, "generated_at": signals["generated_at"], "source": source,
            "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "salt": crypto.b64(salt), "iterations": crypto.ITERATIONS}, indent=2).encode(),
    }
    for f in sorted((PUBLIC / "charts").glob("*.json")):
        files[f"enc/charts/{f.stem}.enc"] = enc(f.read_bytes())
    # Last safety net: refuse to publish anything that contains one of your keys.
    for path, content in files.items():
        text = content.decode("utf-8", "ignore")
        for secret in env.secrets() + [passphrase]:
            if secret and len(secret) >= 6 and secret in text:
                raise SystemExit(f"Refusing to publish: {path} contains a key or the passphrase.")
    return files


def publish(source="pc", quiet=False):
    """Build and upload. Returns a short status line. Raises GitHubError on upload problems."""
    token, repo, passphrase, missing = settings()
    if missing:
        return f"not configured (add {', '.join(missing)} to .env)"
    files = build(repo, passphrase, source)
    size = sum(len(v) for v in files.values())
    gh = Repo(token, repo)
    sha = gh.put_files(BRANCH, files, f"Dashboard update from {source}", orphan=True)
    if source == "actions":
        gh.request_pages_build()
    return f"published {len(files)} files ({size / 1e6:.1f} MB) to {repo}@{BRANCH} ({sha[:7]})"


def main():
    source = "actions" if "--source" in sys.argv and "actions" in sys.argv else "pc"
    if "--preview" in sys.argv:
        _, repo, passphrase, _ = settings()
        repo, passphrase = repo or "preview/signal-dashboard", passphrase or "preview passphrase"
        out = store.DATA / "site_preview"
        for path, content in build(repo, passphrase, source).items():
            (out / path).parent.mkdir(parents=True, exist_ok=True)
            (out / path).write_bytes(content)
        print(f"Preview built in {out} (repo {repo!r}, passphrase {'from .env' if env.get('DASHBOARD_PASSPHRASE') else repr(passphrase)})")
        return 0
    try:
        print(publish(source))
        return 0
    except GitHubError as e:
        print(f"Upload failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
