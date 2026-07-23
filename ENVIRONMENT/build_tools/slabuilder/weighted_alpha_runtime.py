"""Trusted installer/resolver for the source-free weighted-alpha runtime."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 128
MAX_MANIFEST_BYTES = 1024 * 1024
_ALLOWED_RUNTIME_SUFFIXES = {".dll", ".exe", ".json", ".rad", ".txt"}
_ALLOWED_EXTENSIONLESS_FILES = {"SHA256SUMS"}
Downloader = Callable[[str, Path, Mapping[str, str]], None]


class WeightedAlphaRuntimeError(RuntimeError):
    """A first-party runtime could not be trusted, installed, or resolved."""


@dataclass(frozen=True)
class ResolvedWeightedAlphaRuntime:
    release: str
    platform: str
    mesa_base_commit: str
    private_source_manifest_sha256: str
    root: Path
    executable: Path
    radius_file: Path
    runtime_manifest: Path
    expected_executable_sha256: str
    expected_radius_sha256: str
    expected_runtime_manifest_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(path: Path, *, maximum_bytes: int = MAX_MANIFEST_BYTES) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        if path.stat().st_size > maximum_bytes:
            raise ValueError(f"JSON file exceeds {maximum_bytes} bytes")
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WeightedAlphaRuntimeError(f"cannot read trusted weighted-alpha metadata: {exc}") from exc
    if not isinstance(payload, dict):
        raise WeightedAlphaRuntimeError("weighted-alpha metadata must be a JSON object")
    return payload


def load_release_index(index_path: Path | str | None = None) -> dict[str, Any]:
    path = (
        Path(index_path)
        if index_path is not None
        else Path(__file__).with_name("data") / "weighted_alpha_releases.json"
    )
    payload = _strict_json(path)
    if payload.get("schema_version") != 1:
        raise WeightedAlphaRuntimeError("unsupported weighted-alpha release-index schema")
    release = payload.get("default_release")
    releases = payload.get("releases")
    if not isinstance(release, str) or not isinstance(releases, dict) or release not in releases:
        raise WeightedAlphaRuntimeError("weighted-alpha release index has no valid default release")
    return payload


def _host_platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower().replace("amd64", "x86_64").replace("x64", "x86_64")
    if system == "windows" and machine == "x86_64":
        return "windows-x86_64"
    return f"{system}-{machine}"


def _cache_root(environ: Mapping[str, str]) -> Path:
    override = environ.get("MESA_WEIGHTED_ALPHA_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    if platform.system().lower() == "windows" and environ.get("LOCALAPPDATA"):
        return (Path(environ["LOCALAPPDATA"]) / "MESA" / "weighted-alpha").resolve()
    return (Path.home() / ".cache" / "mesa" / "weighted-alpha").resolve()


def _release_platform(
    index: Mapping[str, Any],
    release: str,
    platform_key: str,
) -> dict[str, Any]:
    releases = index.get("releases")
    release_entry = releases.get(release) if isinstance(releases, dict) else None
    platforms = release_entry.get("platforms") if isinstance(release_entry, dict) else None
    entry = platforms.get(platform_key) if isinstance(platforms, dict) else None
    if not isinstance(entry, dict):
        raise WeightedAlphaRuntimeError(
            f"weighted-alpha release {release!r} has unsupported platform {platform_key!r}"
        )
    if not isinstance(release_entry, dict):
        raise WeightedAlphaRuntimeError("weighted-alpha release-index entry is invalid")
    mesa_base_commit = release_entry.get("mesa_base_commit")
    source_manifest_sha256 = release_entry.get("private_source_manifest_sha256")
    if (
        not isinstance(mesa_base_commit, str)
        or len(mesa_base_commit) != 40
        or any(character not in "0123456789abcdef" for character in mesa_base_commit)
        or not isinstance(source_manifest_sha256, str)
        or len(source_manifest_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_manifest_sha256)
    ):
        raise WeightedAlphaRuntimeError("weighted-alpha release source provenance is invalid")
    required_strings = {
        "asset_api_url",
        "asset_name",
        "archive_sha256",
        "archive_root",
        "runtime_manifest",
        "runtime_manifest_sha256",
        "executable",
        "executable_sha256",
        "radius_table",
        "radius_table_sha256",
    }
    if any(not isinstance(entry.get(name), str) or not entry[name] for name in required_strings):
        raise WeightedAlphaRuntimeError("weighted-alpha release-index platform entry is incomplete")
    if type(entry.get("asset_size")) is not int or not 0 < entry["asset_size"] <= MAX_ARCHIVE_BYTES:
        raise WeightedAlphaRuntimeError("weighted-alpha release-index asset_size is invalid")
    for name in (
        "archive_sha256",
        "runtime_manifest_sha256",
        "executable_sha256",
        "radius_table_sha256",
    ):
        value = entry[name]
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise WeightedAlphaRuntimeError(f"weighted-alpha release index has invalid {name}")
    result = dict(entry)
    result["mesa_base_commit"] = mesa_base_commit
    result["private_source_manifest_sha256"] = source_manifest_sha256
    return result


class _AuthorizationStrippingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep GitHub credentials on-origin, never on signed asset redirects."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> urllib.request.Request | None:
        redirected = super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )
        if redirected is not None:
            source = urllib.parse.urlsplit(request.full_url).netloc.casefold()
            target = urllib.parse.urlsplit(new_url).netloc.casefold()
            if source != target:
                redirected.remove_header("Authorization")
        return redirected


def _open_github_request(request: urllib.request.Request) -> Any:
    opener = urllib.request.build_opener(_AuthorizationStrippingRedirectHandler())
    return opener.open(request, timeout=120)


def _download_github_asset(
    url: str,
    destination: Path,
    environ: Mapping[str, str],
) -> None:
    token = environ.get("GH_TOKEN") or environ.get("GITHUB_TOKEN")
    if not token:
        gh = shutil.which("gh")
        if not gh:
            raise WeightedAlphaRuntimeError(
                "private weighted-alpha runtime download requires GH_TOKEN, GITHUB_TOKEN, or authenticated gh"
            )
        try:
            completed = subprocess.run(
                [gh, "auth", "token", "--hostname", "github.com"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WeightedAlphaRuntimeError(f"weighted-alpha gh authentication failed: {exc}") from exc
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise WeightedAlphaRuntimeError(f"weighted-alpha gh authentication failed: {stderr}")
        token = completed.stdout.decode("utf-8", errors="strict").strip()
        if not token or len(token) > 4096 or any(character.isspace() for character in token):
            raise WeightedAlphaRuntimeError("weighted-alpha gh returned an invalid authentication token")

    parsed = urllib.parse.urlsplit(url)
    asset_prefix = "/repos/GuGroup/mesa/releases/assets/"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.github.com"
        or not parsed.path.startswith(asset_prefix)
        or not parsed.path.removeprefix(asset_prefix).isdigit()
        or parsed.query
        or parsed.fragment
    ):
        raise WeightedAlphaRuntimeError("weighted-alpha asset URL is not a trusted GitHub API URL")

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {token}",
            "User-Agent": "GuGroup-MESA-weighted-alpha-resolver",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with _open_github_request(request) as response, destination.open("wb") as output:
            total = 0
            while True:
                chunk = response.read(min(1024 * 1024, MAX_ARCHIVE_BYTES - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise WeightedAlphaRuntimeError(
                        "weighted-alpha archive download exceeds the size limit"
                    )
                output.write(chunk)
    except WeightedAlphaRuntimeError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError) as exc:
        destination.unlink(missing_ok=True)
        raise WeightedAlphaRuntimeError(f"weighted-alpha GitHub asset download failed: {exc}") from exc


def _safe_member_path(
    name: str,
    archive_root: str,
    *,
    is_directory: bool = False,
) -> Path:
    if "\\" in name or ":" in name or "\x00" in name:
        raise WeightedAlphaRuntimeError(f"unsafe weighted-alpha archive path: {name!r}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise WeightedAlphaRuntimeError(f"unsafe weighted-alpha archive path: {name!r}")
    if pure.parts[0] != archive_root:
        raise WeightedAlphaRuntimeError("weighted-alpha archive has an unexpected top-level root")
    relative = PurePosixPath(*pure.parts[1:])
    if not relative.parts:
        return Path(".")
    if not is_directory and (
        relative.name not in _ALLOWED_EXTENSIONLESS_FILES
        and relative.suffix.casefold() not in _ALLOWED_RUNTIME_SUFFIXES
    ):
        raise WeightedAlphaRuntimeError(
            f"weighted-alpha binary bundle violates the source-free boundary: {name!r}"
        )
    return Path(*relative.parts)


def _extract_verified_archive(archive: Path, destination: Path, entry: Mapping[str, Any]) -> Path:
    try:
        with zipfile.ZipFile(archive) as handle:
            members = handle.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise WeightedAlphaRuntimeError("weighted-alpha archive contains too many members")
            total = sum(item.file_size for item in members)
            if total > MAX_EXTRACTED_BYTES:
                raise WeightedAlphaRuntimeError("weighted-alpha archive expands beyond the size limit")
            root = destination / entry["archive_root"]
            for member in members:
                relative = _safe_member_path(
                    member.filename,
                    entry["archive_root"],
                    is_directory=member.is_dir(),
                )
                unix_mode = member.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise WeightedAlphaRuntimeError("weighted-alpha archive may not contain symlinks")
                if relative == Path(".") or member.is_dir():
                    continue
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
    except (OSError, zipfile.BadZipFile) as exc:
        raise WeightedAlphaRuntimeError(f"cannot extract weighted-alpha runtime: {exc}") from exc
    return root


def _load_sha256sums(path: Path) -> dict[str, str]:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("SHA256SUMS exceeds the size limit")
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError, ValueError) as exc:
        raise WeightedAlphaRuntimeError(f"cannot read weighted-alpha SHA256SUMS: {exc}") from exc
    checksums: dict[str, str] = {}
    for line in lines:
        digest, separator, relative_name = line.partition("  ")
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not relative_name
            or relative_name in checksums
        ):
            raise WeightedAlphaRuntimeError("weighted-alpha SHA256SUMS is not canonical")
        checksums[relative_name] = digest
    if not checksums:
        raise WeightedAlphaRuntimeError("weighted-alpha SHA256SUMS is empty")
    return checksums


def _validate_runtime(
    root: Path,
    release: str,
    platform_key: str,
    entry: Mapping[str, Any],
) -> ResolvedWeightedAlphaRuntime:
    if root.is_symlink() or not root.is_dir():
        raise WeightedAlphaRuntimeError(f"weighted-alpha cache entry is not a regular directory: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise WeightedAlphaRuntimeError("weighted-alpha runtime cache may not contain symlinks")
        relative = path.relative_to(root)
        _safe_member_path(
            f"{entry['archive_root']}/{relative.as_posix()}",
            entry["archive_root"],
            is_directory=path.is_dir(),
        )

    manifest_path = root / entry["runtime_manifest"]
    if not manifest_path.is_file() or _sha256(manifest_path) != entry["runtime_manifest_sha256"]:
        raise WeightedAlphaRuntimeError("weighted-alpha runtime manifest SHA-256 mismatch")
    manifest = _strict_json(manifest_path)
    if manifest.get("schema_version") != 1 or manifest.get("graph_schema_version") != 1:
        raise WeightedAlphaRuntimeError("unsupported weighted-alpha runtime manifest schema")
    if manifest.get("engine_release") != release or manifest.get("platform") != platform_key:
        raise WeightedAlphaRuntimeError("weighted-alpha runtime manifest release/platform mismatch")
    if (
        manifest.get("mesa_base_commit") != entry["mesa_base_commit"]
        or manifest.get("private_source_manifest_sha256")
        != entry["private_source_manifest_sha256"]
    ):
        raise WeightedAlphaRuntimeError("weighted-alpha runtime source provenance mismatch")
    if manifest.get("entrypoint") != entry["executable"]:
        raise WeightedAlphaRuntimeError("weighted-alpha runtime manifest entrypoint mismatch")
    if manifest.get("radius_table") != entry["radius_table"]:
        raise WeightedAlphaRuntimeError("weighted-alpha runtime manifest radius-table mismatch")
    contract = manifest.get("parameter_contract")
    if not isinstance(contract, dict) or contract.get("-a") != "contact_anchor_radius_angstrom":
        raise WeightedAlphaRuntimeError("weighted-alpha runtime has an incompatible -a parameter contract")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise WeightedAlphaRuntimeError("weighted-alpha runtime manifest has no artifacts")
    expected_files = set(artifacts) | {entry["runtime_manifest"], "SHA256SUMS"}
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise WeightedAlphaRuntimeError("weighted-alpha runtime files do not exactly match the manifest")
    for relative_name, digest in artifacts.items():
        if not isinstance(relative_name, str) or not isinstance(digest, str):
            raise WeightedAlphaRuntimeError("weighted-alpha runtime artifact entry is invalid")
        relative = _safe_member_path(
            f"{entry['archive_root']}/{relative_name}", entry["archive_root"]
        )
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise WeightedAlphaRuntimeError("weighted-alpha runtime artifact digest is invalid")
        path = root / relative
        if not path.is_file() or _sha256(path) != digest:
            raise WeightedAlphaRuntimeError(
                f"weighted-alpha runtime artifact SHA-256 mismatch: {relative_name}"
            )

    expected_checksums = dict(artifacts)
    expected_checksums[entry["runtime_manifest"]] = entry["runtime_manifest_sha256"]
    if _load_sha256sums(root / "SHA256SUMS") != expected_checksums:
        raise WeightedAlphaRuntimeError("weighted-alpha SHA256SUMS does not match the manifest")

    executable = root / entry["executable"]
    radius_file = root / entry["radius_table"]
    if _sha256(executable) != entry["executable_sha256"]:
        raise WeightedAlphaRuntimeError("weighted-alpha executable SHA-256 mismatch")
    if _sha256(radius_file) != entry["radius_table_sha256"]:
        raise WeightedAlphaRuntimeError("weighted-alpha radius-table SHA-256 mismatch")
    return ResolvedWeightedAlphaRuntime(
        release=release,
        platform=platform_key,
        mesa_base_commit=entry["mesa_base_commit"],
        private_source_manifest_sha256=entry["private_source_manifest_sha256"],
        root=root.resolve(),
        executable=executable.resolve(),
        radius_file=radius_file.resolve(),
        runtime_manifest=manifest_path.resolve(),
        expected_executable_sha256=entry["executable_sha256"],
        expected_radius_sha256=entry["radius_table_sha256"],
        expected_runtime_manifest_sha256=entry["runtime_manifest_sha256"],
    )


def install_first_party_runtime(
    *,
    index_path: Path | str | None = None,
    cache_root: Path | str | None = None,
    release: str | None = None,
    platform_key: str | None = None,
    environ: Mapping[str, str] | None = None,
    downloader: Downloader | None = None,
) -> ResolvedWeightedAlphaRuntime:
    env = os.environ if environ is None else environ
    index = load_release_index(index_path)
    selected_release = release or index["default_release"]
    selected_platform = platform_key or _host_platform_key()
    entry = _release_platform(index, selected_release, selected_platform)
    cache = Path(cache_root).resolve() if cache_root is not None else _cache_root(env)
    final_root = cache / selected_release / selected_platform
    if final_root.exists():
        return _validate_runtime(final_root, selected_release, selected_platform, entry)

    cache.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".weighted-alpha-install-", dir=cache))
    try:
        archive = temporary / entry["asset_name"]
        (downloader or _download_github_asset)(entry["asset_api_url"], archive, env)
        if not archive.is_file() or archive.stat().st_size != entry["asset_size"]:
            raise WeightedAlphaRuntimeError("weighted-alpha archive size mismatch")
        if _sha256(archive) != entry["archive_sha256"]:
            raise WeightedAlphaRuntimeError("weighted-alpha archive SHA-256 mismatch")
        extracted = _extract_verified_archive(archive, temporary / "extracted", entry)
        runtime = _validate_runtime(extracted, selected_release, selected_platform, entry)
        final_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(extracted, final_root)
        except OSError:
            if not final_root.exists():
                raise
        return _validate_runtime(final_root, selected_release, selected_platform, entry)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def resolve_first_party_runtime(
    *,
    index_path: Path | str | None = None,
    cache_root: Path | str | None = None,
    release: str | None = None,
    platform_key: str | None = None,
    auto_install: bool = True,
    environ: Mapping[str, str] | None = None,
    downloader: Downloader | None = None,
) -> ResolvedWeightedAlphaRuntime:
    env = os.environ if environ is None else environ
    index = load_release_index(index_path)
    selected_release = release or index["default_release"]
    selected_platform = platform_key or _host_platform_key()
    entry = _release_platform(index, selected_release, selected_platform)
    cache = Path(cache_root).resolve() if cache_root is not None else _cache_root(env)
    final_root = cache / selected_release / selected_platform
    if final_root.exists():
        return _validate_runtime(final_root, selected_release, selected_platform, entry)
    if not auto_install:
        raise WeightedAlphaRuntimeError(
            f"verified weighted-alpha runtime is not installed at {final_root}"
        )
    return install_first_party_runtime(
        index_path=index_path,
        cache_root=cache,
        release=selected_release,
        platform_key=selected_platform,
        environ=env,
        downloader=downloader,
    )
