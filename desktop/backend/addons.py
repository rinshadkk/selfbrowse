"""Optional add-ons the packaged app can download after it is installed (today: Presidio).

The packaged backend has no Python or pip, so an add-on is a ready-made program published as a release file.
``addon_manifest.json`` (shipped inside the app) pins the address, size and SHA-256 of that file; nothing is
unpacked unless the download matches the hash. The add-on then runs as its own process on 127.0.0.1 and the
backend talks to it (see ``presidio_sidecar.py``).

Where things live: ``<app data>/addons/presidio/`` holds the unpacked program and ``installed.json``.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import select
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

NAME = "presidio"
PROGRAM = "presidio-sidecar"                      # folder inside the zip, and the program inside that folder
START_TIMEOUT = 90.0                              # seconds to wait for the add-on to say which port it uses
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # 127.0.0.1 never goes through a proxy


def data_dir() -> Path:
    return Path(os.environ.get("SB_DESKTOP_DATA") or Path.home() / ".selfbrowse-desktop") / "addons" / NAME


def manifest() -> dict[str, Any]:
    """The pinned add-on file: ``{file, url, sha256, size, version}``. ``SB_ADDON_MANIFEST`` points elsewhere (tests, local builds)."""
    path = os.environ.get("SB_ADDON_MANIFEST")
    if not path:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        path = str(base / "addon_manifest.json")
    try:
        return dict(json.loads(Path(path).read_text())[NAME])
    except (OSError, ValueError, KeyError):
        return {}


def _program() -> Path:
    return data_dir() / PROGRAM / PROGRAM


def installed() -> bool:
    return _program().is_file() and (data_dir() / "installed.json").is_file()


def unavailable_reason() -> str:
    """Why this build cannot offer the download, or '' when it can."""
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return "The Presidio add-on is only built for Macs with Apple Silicon."
    m = manifest()
    if not (m.get("url") and m.get("sha256") and m.get("size")):
        return "The Presidio add-on has not been published for this version yet."
    return ""


# ── download and unpack ────────────────────────────────────────────────────────────────────────

JOB: dict[str, Any] = {"state": "idle", "error": "", "phase": "", "progress": 0.0}   # idle | running | done | error
_cancel = threading.Event()


def status() -> dict[str, Any]:
    m = manifest()
    why = unavailable_reason()
    if installed():
        state = "done"
    elif why and JOB["state"] != "running":
        state = "unavailable"
    else:
        state = JOB["state"] if JOB["state"] in ("running", "error") else "idle"
    return {"state": state, "error": why if state == "unavailable" else JOB["error"], "phase": JOB["phase"],
            "progress": round(JOB["progress"], 3), "size": int(m.get("size") or 0),
            "host": urllib.parse.urlparse(m.get("url") or "").hostname or "", "packaged": True}


def _check_url(url: str) -> None:
    scheme = urllib.parse.urlparse(url).scheme
    if scheme != "https" and not (scheme == "file" and os.environ.get("SB_ADDON_MANIFEST")):
        raise RuntimeError("The add-on address must start with https://.")


def _download(url: str, dest: Path, size: int, sha256: str) -> None:
    _check_url(url)
    digest, got = hashlib.sha256(), 0
    with _opener.open(url, timeout=60) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            if _cancel.is_set():
                raise RuntimeError("Cancelled.")
            got += len(chunk)
            if got > size:
                raise RuntimeError("The download is larger than expected, so it was stopped.")
            digest.update(chunk)
            out.write(chunk)
            JOB["progress"] = got / size
    if got != size or digest.hexdigest() != sha256.lower():
        raise RuntimeError("The download does not match the checksum this app expects. Nothing was installed.")


def _extract(archive: Path, into: Path) -> None:
    """Unpack a zip, refusing anything that would land outside ``into``. Keeps the program's executable bit."""
    root = into.resolve()
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        for i, info in enumerate(members):
            target = (into / info.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("The add-on file is not safe to unpack.")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                link = z.read(info).decode()
                dest = (target.parent / link).resolve()
                if os.path.isabs(link) or (root != dest and root not in dest.parents):
                    raise RuntimeError("The add-on file is not safe to unpack.")
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(link, target)
            elif info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                os.chmod(target, (mode & 0o777) or 0o644)
            JOB["progress"] = (i + 1) / len(members)


def _smoke_test() -> None:
    """Start the unpacked program and have it find a name and an address, so a broken file is caught now."""
    box = Sidecar()
    try:
        found = box.analyze("My name is John Smith and my email is john.smith@example.com.", None, 0.4)
        if not any(r["entity_type"] in ("PERSON", "EMAIL_ADDRESS") for r in found):
            raise RuntimeError("The add-on started but did not find anything in a test sentence.")
    finally:
        box.stop()


def _install_job(m: dict[str, Any]) -> None:
    root = data_dir()
    part, tmp = root.parent / f"{NAME}.zip.part", root.parent / f"{NAME}.unpacking"
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        JOB.update(phase="download", progress=0.0)
        _download(m["url"], part, int(m["size"]), m["sha256"])
        JOB.update(phase="unpack", progress=0.0)
        shutil.rmtree(tmp, ignore_errors=True)
        _extract(part, tmp)
        part.unlink(missing_ok=True)
        if not (tmp / PROGRAM / PROGRAM).is_file():
            raise RuntimeError("The add-on file does not contain the program.")
        shutil.rmtree(root, ignore_errors=True)
        tmp.rename(root)
        (root / "installed.json").write_text(json.dumps({"version": m.get("version", ""), "sha256": m["sha256"]}))
        JOB.update(phase="check", progress=1.0)
        try:
            _smoke_test()
        except Exception:
            remove()
            raise
        JOB.update(state="done", error="", phase="")
    except Exception as exc:
        part.unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
        JOB.update(state="error", error=str(exc)[:300], phase="")


def start_install() -> dict[str, Any]:
    """Begin the download in the background. The caller has the person's consent."""
    if installed():
        return status()
    why = unavailable_reason()
    if why:
        raise RuntimeError(why)
    if JOB["state"] == "running":
        raise ValueError("Presidio is already being installed.")
    _cancel.clear()
    JOB.update(state="running", error="", phase="download", progress=0.0)
    threading.Thread(target=_install_job, args=(manifest(),), daemon=True).start()
    return status()


def cancel() -> None:
    _cancel.set()


def remove() -> None:
    """Stop the add-on and delete it from disk."""
    SIDECAR.stop()
    shutil.rmtree(data_dir(), ignore_errors=True)
    JOB.update(state="idle", error="", phase="", progress=0.0)


# ── running the add-on ─────────────────────────────────────────────────────────────────────────

class Sidecar:
    """The Presidio program on 127.0.0.1. Started when first needed, restarted if it quit, stopped with the backend."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.token = ""
        self._lock = threading.Lock()

    def _alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _start(self) -> None:
        if not _program().is_file():
            raise RuntimeError("The Presidio add-on is not installed.")
        self.token = secrets.token_urlsafe(24)
        self.proc = subprocess.Popen([str(_program())], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                     env={**os.environ, "SB_ADDON_TOKEN": self.token})
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if select.select([self.proc.stdout], [], [], 0.5)[0]:
                line = self.proc.stdout.readline().strip()
                if line.isdigit():
                    self.port = int(line)
                    return
                break
            if self.proc.poll() is not None:
                break
        self.stop()
        raise RuntimeError("The Presidio add-on did not start. Remove it and install it again.")

    def ensure(self) -> None:
        with self._lock:
            if not self._alive():
                self._start()

    def _call(self, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers={"X-Addon-Token": self.token},
                                     data=json.dumps(body).encode() if body is not None else None)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with _opener.open(req, timeout=120) as resp:
            return json.loads(resp.read())

    def analyze(self, text: str, entities: list[str] | None, threshold: float) -> list[dict[str, Any]]:
        self.ensure()
        try:
            return self._call("/analyze", {"text": text, "entities": entities or [], "threshold": threshold})["results"]
        except OSError:                                   # it quit while idle: start it once more
            self.stop()
            self.ensure()
            return self._call("/analyze", {"text": text, "entities": entities or [], "threshold": threshold})["results"]

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


SIDECAR = Sidecar()


class RemoteAnalyzer:
    """Looks like Presidio's ``AnalyzerEngine`` to ``PresidioRedact``, but asks the add-on program."""

    def analyze(self, text: str, language: str = "en", entities: Any = None, score_threshold: float = 0.4, **_: Any) -> list[Any]:
        return [SimpleNamespace(**r) for r in SIDECAR.analyze(text, list(entities) if entities else None, score_threshold)]
