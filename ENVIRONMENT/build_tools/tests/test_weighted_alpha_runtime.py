from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

import pytest

import slabuilder.weighted_alpha_runtime as runtime
from slabuilder.weighted_alpha_runtime import (
    WeightedAlphaRuntimeError,
    install_first_party_runtime,
    load_release_index,
    resolve_first_party_runtime,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_fixture_release(tmp_path: Path, *, extra_name: str | None = None) -> tuple[Path, Path]:
    root_name = "weighted-alpha-test"
    payload = tmp_path / root_name
    payload.mkdir()
    executable = b"synthetic-executable"
    radius = b"H 1.0\n"
    (payload / "weighted_alpha_complex.exe").write_bytes(executable)
    (payload / "atomic_radii_UFF.rad").write_bytes(radius)
    artifacts = {
        "atomic_radii_UFF.rad": _sha(radius),
        "weighted_alpha_complex.exe": _sha(executable),
    }
    if extra_name:
        extra_path = payload / extra_name
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_bytes(b"forbidden")
        artifacts[extra_name] = _sha(b"forbidden")
    manifest = {
        "schema_version": 1,
        "engine_release": "weighted-alpha-test-v1",
        "platform": "windows-x86_64",
        "mesa_base_commit": "a" * 40,
        "private_source_manifest_sha256": "b" * 64,
        "entrypoint": "weighted_alpha_complex.exe",
        "radius_table": "atomic_radii_UFF.rad",
        "graph_schema_version": 1,
        "parameter_contract": {
            "-a": "contact_anchor_radius_angstrom",
            "--alpha-factor": "weighted_alpha_construction_factor",
        },
        "artifacts": artifacts,
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (payload / "runtime_manifest.json").write_bytes(manifest_bytes)
    checksum_entries = {**artifacts, "runtime_manifest.json": _sha(manifest_bytes)}
    checksum_text = "".join(
        f"{digest}  {name}\n" for name, digest in sorted(checksum_entries.items())
    )
    (payload / "SHA256SUMS").write_text(checksum_text, encoding="utf-8")
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                handle.write(path, (Path(root_name) / path.relative_to(payload)).as_posix())
    index = {
        "schema_version": 1,
        "default_release": "weighted-alpha-test-v1",
        "releases": {
            "weighted-alpha-test-v1": {
                "mesa_base_commit": "a" * 40,
                "private_source_manifest_sha256": "b" * 64,
                "platforms": {
                    "windows-x86_64": {
                        "asset_api_url": "https://example.invalid/runtime.zip",
                        "asset_name": "runtime.zip",
                        "asset_size": archive.stat().st_size,
                        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                        "archive_root": root_name,
                        "runtime_manifest": "runtime_manifest.json",
                        "runtime_manifest_sha256": _sha(manifest_bytes),
                        "executable": "weighted_alpha_complex.exe",
                        "executable_sha256": _sha(executable),
                        "radius_table": "atomic_radii_UFF.rad",
                        "radius_table_sha256": _sha(radius),
                    }
                }
            }
        },
    }
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return archive, index_path


def _copy_downloader(archive: Path):
    def download(_url: str, destination: Path, _environ: dict[str, str]) -> None:
        shutil.copy2(archive, destination)

    return download


def test_bundled_release_index_pins_private_draft_asset() -> None:
    index = load_release_index()
    assert index["default_release"] == "weighted-alpha-binary-v0.1.0-alpha.1"
    platform = index["releases"][index["default_release"]]["platforms"]["windows-x86_64"]
    assert platform["asset_api_url"].endswith("/487574946")
    assert platform["asset_size"] == 1987284
    assert platform["archive_sha256"] == "76fde0666e297fed95f41dee3fe73449b8b960eeb299572927b813929978b7a1"


def test_install_and_resolve_verified_versioned_cache(tmp_path: Path) -> None:
    archive, index_path = _write_fixture_release(tmp_path)
    cache = tmp_path / "cache"
    installed = install_first_party_runtime(
        index_path=index_path,
        cache_root=cache,
        platform_key="windows-x86_64",
        environ={},
        downloader=_copy_downloader(archive),
    )
    assert installed.executable.read_bytes() == b"synthetic-executable"
    assert installed.radius_file.read_text(encoding="utf-8") == "H 1.0\n"
    resolved = resolve_first_party_runtime(
        index_path=index_path,
        cache_root=cache,
        platform_key="windows-x86_64",
        auto_install=False,
        environ={},
    )
    assert resolved == installed
    assert resolved.release == "weighted-alpha-test-v1"
    assert resolved.mesa_base_commit == "a" * 40
    assert resolved.private_source_manifest_sha256 == "b" * 64


def test_cached_runtime_tamper_is_rejected(tmp_path: Path) -> None:
    archive, index_path = _write_fixture_release(tmp_path)
    installed = install_first_party_runtime(
        index_path=index_path,
        cache_root=tmp_path / "cache",
        platform_key="windows-x86_64",
        environ={},
        downloader=_copy_downloader(archive),
    )
    installed.executable.write_bytes(b"tampered")
    with pytest.raises(WeightedAlphaRuntimeError, match="SHA-256"):
        resolve_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="windows-x86_64",
            auto_install=False,
            environ={},
        )


@pytest.mark.parametrize(
    "source_name",
    ["private.cpp", "private.ipp", "private.inl", "private.inc", "private.tpp", "private.cu", "private.cuh", "nested-source.zip"],
)
def test_binary_bundle_rejects_non_runtime_artifact(
    tmp_path: Path, source_name: str
) -> None:
    archive, index_path = _write_fixture_release(tmp_path, extra_name=source_name)
    with pytest.raises(WeightedAlphaRuntimeError, match="source-free"):
        install_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="windows-x86_64",
            environ={},
            downloader=_copy_downloader(archive),
        )


def test_unsupported_platform_fails_closed(tmp_path: Path) -> None:
    _, index_path = _write_fixture_release(tmp_path)
    with pytest.raises(WeightedAlphaRuntimeError, match="unsupported"):
        resolve_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="linux-x86_64",
            auto_install=False,
            environ={},
        )


def test_archive_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive, index_path = _write_fixture_release(tmp_path)
    with zipfile.ZipFile(archive, "a") as handle:
        handle.writestr("weighted-alpha-test/../escape.dll", b"escape")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = index["releases"]["weighted-alpha-test-v1"]["platforms"]["windows-x86_64"]
    entry["asset_size"] = archive.stat().st_size
    entry["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(WeightedAlphaRuntimeError, match="unsafe weighted-alpha archive path"):
        install_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="windows-x86_64",
            environ={},
            downloader=_copy_downloader(archive),
        )


def test_archive_sha256_tamper_is_rejected(tmp_path: Path) -> None:
    archive, index_path = _write_fixture_release(tmp_path)

    def tampered_download(_url: str, destination: Path, _environ: dict[str, str]) -> None:
        data = bytearray(archive.read_bytes())
        data[len(data) // 2] ^= 1
        destination.write_bytes(data)

    with pytest.raises(WeightedAlphaRuntimeError, match="archive SHA-256"):
        install_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="windows-x86_64",
            environ={},
            downloader=tampered_download,
        )


def test_cached_runtime_extra_file_is_rejected(tmp_path: Path) -> None:
    archive, index_path = _write_fixture_release(tmp_path)
    installed = install_first_party_runtime(
        index_path=index_path,
        cache_root=tmp_path / "cache",
        platform_key="windows-x86_64",
        environ={},
        downloader=_copy_downloader(archive),
    )
    (installed.root / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(WeightedAlphaRuntimeError, match="exactly match"):
        resolve_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="windows-x86_64",
            auto_install=False,
            environ={},
        )


def test_cached_sha256sums_tamper_is_rejected(tmp_path: Path) -> None:
    archive, index_path = _write_fixture_release(tmp_path)
    installed = install_first_party_runtime(
        index_path=index_path,
        cache_root=tmp_path / "cache",
        platform_key="windows-x86_64",
        environ={},
        downloader=_copy_downloader(archive),
    )
    (installed.root / "SHA256SUMS").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(WeightedAlphaRuntimeError, match="SHA256SUMS"):
        resolve_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="windows-x86_64",
            auto_install=False,
            environ={},
        )


def test_release_source_provenance_mismatch_is_rejected(tmp_path: Path) -> None:
    archive, index_path = _write_fixture_release(tmp_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["releases"]["weighted-alpha-test-v1"]["private_source_manifest_sha256"] = "c" * 64
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(WeightedAlphaRuntimeError, match="source provenance"):
        install_first_party_runtime(
            index_path=index_path,
            cache_root=tmp_path / "cache",
            platform_key="windows-x86_64",
            environ={},
            downloader=_copy_downloader(archive),
        )


@pytest.mark.parametrize(
    "member_name",
    [
        "weighted-alpha-test/..\\escape.dll",
        "weighted-alpha-test/sub\\..\\..\\escape.dll",
        "weighted-alpha-test/weighted_alpha_complex.exe:payload",
    ],
)
def test_archive_windows_separator_and_ads_paths_are_rejected(member_name: str) -> None:
    with pytest.raises(WeightedAlphaRuntimeError, match="unsafe weighted-alpha archive path"):
        runtime._safe_member_path(member_name, "weighted-alpha-test")


def test_authenticated_download_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "MAX_ARCHIVE_BYTES", 8)
    monkeypatch.setattr(
        runtime,
        "_open_github_request",
        lambda _request: io.BytesIO(b"x" * 9),
    )
    with pytest.raises(WeightedAlphaRuntimeError, match="size limit"):
        runtime._download_github_asset(
            "https://api.github.com/repos/GuGroup/mesa/releases/assets/1",
            tmp_path / "download.zip",
            {"GH_TOKEN": "test-token"},
        )


def test_authenticated_gh_cli_supplies_token_to_bounded_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "gh" if name == "gh" else None)

    def fake_run(command: list[str], **_kwargs: object):
        assert command == ["gh", "auth", "token", "--hostname", "github.com"]
        return runtime.subprocess.CompletedProcess(command, 0, b"from-gh\n", b"")

    def fake_urlopen(request: object, **_kwargs: object):
        assert request.get_header("Authorization") == "Bearer from-gh"
        return io.BytesIO(b"runtime")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(runtime, "_open_github_request", fake_urlopen)
    destination = tmp_path / "download.zip"
    runtime._download_github_asset(
        "https://api.github.com/repos/GuGroup/mesa/releases/assets/1",
        destination,
        {},
    )
    assert destination.read_bytes() == b"runtime"


def test_cross_origin_redirect_strips_authorization() -> None:
    handler = runtime._AuthorizationStrippingRedirectHandler()
    request = runtime.urllib.request.Request(
        "https://api.github.com/repos/GuGroup/mesa/releases/assets/1",
        headers={"Authorization": "Bearer secret", "Accept": "application/octet-stream"},
    )
    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://objects.githubusercontent.com/signed-asset",
    )
    assert redirected is not None
    assert redirected.get_header("Authorization") is None
    assert redirected.get_header("Accept") == "application/octet-stream"
