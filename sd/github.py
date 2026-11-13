"""Minimal GitHub REST client: upload files to a branch in ONE commit, with no git installed.

Uses the Git Data API: blobs (file contents) -> a tree (folder listing) -> a commit -> move the branch.
The token only needs "Contents: read and write" on this one repository.
"""
import base64

import requests

from . import env

API = "https://api.github.com"


class GitHubError(Exception):
    pass


class Repo:
    def __init__(self, token, full_name):
        self.full = full_name
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "signal-dashboard"})

    def _call(self, method, path, ok=(200, 201), **kw):
        r = self.s.request(method, f"{API}/repos/{self.full}{path}", timeout=60, **kw)
        if r.status_code not in ok:
            raise GitHubError(env.scrub(f"GitHub {method} {path}: HTTP {r.status_code} {r.text[:300]}"))
        return r.json() if r.text else {}

    def ref(self, branch):
        """Commit SHA at the tip of `branch`, or None if the branch doesn't exist."""
        r = self.s.get(f"{API}/repos/{self.full}/git/ref/heads/{branch}", timeout=60)
        if r.status_code == 404:
            return None
        if r.status_code == 409:              # a completely empty repository
            return None
        if r.status_code != 200:
            raise GitHubError(env.scrub(f"GitHub ref {branch}: HTTP {r.status_code} {r.text[:300]}"))
        return r.json()["object"]["sha"]

    def is_empty(self):
        r = self.s.get(f"{API}/repos/{self.full}/git/refs", timeout=60)
        return r.status_code == 409 or (r.status_code == 200 and not r.json())

    def first_commit(self):
        """An empty repository can't take blobs yet: create a first README (on the default branch)."""
        self._call("PUT", "/contents/README.md", json={
            "message": "Initial commit", "content": base64.b64encode(b"# signal-dashboard\n").decode()})

    def put_files(self, branch, files, message, orphan=False):
        """Upload {path: bytes} to `branch` in one commit.

        orphan=False: a normal commit on top of the branch (other files stay).
        orphan=True:  the branch is REPLACED by a single commit holding exactly these files
                      (used for the website, so its history never piles up).
        Returns the new commit SHA.
        """
        if self.is_empty():
            self.first_commit()
        entries = []
        for path, content in sorted(files.items()):
            blob = self._call("POST", "/git/blobs", json={"content": base64.b64encode(content).decode(),
                                                          "encoding": "base64"})
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        parent = None if orphan else self.ref(branch)
        tree_req = {"tree": entries}
        if parent:
            tree_req["base_tree"] = self._call("GET", f"/git/commits/{parent}")["tree"]["sha"]
        tree = self._call("POST", "/git/trees", json=tree_req)
        commit = self._call("POST", "/git/commits", json={"message": message, "tree": tree["sha"],
                                                          "parents": [parent] if parent else []})
        if self.ref(branch) is None:
            self._call("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
        else:
            self._call("PATCH", f"/git/refs/heads/{branch}", json={"sha": commit["sha"], "force": orphan})
        return commit["sha"]

    def request_pages_build(self):
        """Ask GitHub to rebuild the Pages site. Needed after uploads made with GitHub Actions' own
        token, because those don't trigger a Pages build by themselves (your PC's token does)."""
        self._call("POST", "/pages/builds", ok=(200, 201))
