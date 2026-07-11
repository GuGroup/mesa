"""Bootstrap preflight checks for platform, secrets, Codex MCP config, and mamba."""
from __future__ import annotations

from .common import *

def env_status(label: str, present: bool, required: bool = False) -> int:
    state = "SET" if present else "MISSING"
    suffix = " REQUIRED" if required and not present else ""
    print(f"  {label}: {state}{suffix}")
    return 1 if required and not present else 0

def print_api_key_help(key_group: str) -> None:
    if key_group == "OPENAI_API_KEY":
        print("    Get an OpenAI API key:")
        print("      https://platform.openai.com/api-keys")
        print("      Help: https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key")
        print("    Add it to DEPENDENCY/.env as:")
        print("      OPENAI_API_KEY=<your key>")
        print("    Note: OpenAI shows the full secret key only once when it is created.")
        return
    if key_group == "MP_API_KEY":
        print("    Get a Materials Project API key:")
        print("      https://next-gen.materialsproject.org/api")
        print("      Docs: https://docs.materialsproject.org/downloading-data/using-the-api/getting-started")
        print("    Add it to DEPENDENCY/.env as:")
        print("      MP_API_KEY=<your key>")
        print("    Legacy fallback also accepted:")
        print("      PMG_MAPI_KEY=<your key>")
        return
    if key_group == "HF_TOKEN":
        print("    Optional Hugging Face token for gated/private checkpoint downloads:")
        print("      https://huggingface.co/settings/tokens")
        print("      Docs: https://huggingface.co/docs/huggingface_hub/en/quick-start")
        print("    Add it to DEPENDENCY/.env as:")
        print("      HF_TOKEN=<your token>")
        print("    Public checkpoints or already-local checkpoints may not need this token.")

def print_codex_config_help() -> None:
    print("    Expected project config location:")
    print("      .codex/config.toml")
    print("    Expected paper_search MCP shape:")
    print("      [mcp_servers.paper_search]")
    print("      enabled = true")
    print("      required = false")
    print('      command = "uv"')
    print('      args = ["run", "--frozen", "-m", "paper_search_mcp.server"]')
    print('      cwd = "EXTERNAL/paper-search-mcp"')
    print("      [mcp_servers.paper_search.env]")
    print(f'      PAPER_SEARCH_MCP_ENV_FILE = "{EXPECTED_PAPER_SEARCH_ENV_FILE}"')

def has_literal_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)

def check_optional_int(label: str, value: Any) -> int:
    if isinstance(value, int) and value > 0:
        print(f"  {label}: OK {value}")
        return 0
    print(f"  {label}: MISSING expected positive integer")
    return 1

def check_paper_search_files() -> int:
    status = 0
    expected_files = [
        "pyproject.toml",
        "uv.lock",
        "paper_search_mcp/server.py",
    ]
    for relpath in expected_files:
        path = EXPECTED_PAPER_SEARCH_CWD / relpath
        if path.is_file():
            print(f"  MCP file {relpath}: OK")
        else:
            print(f"  MCP file {relpath}: MISSING {path}")
            status = 1
    return status

def check_codex_cli_mcp_visibility() -> int:
    codex = find_tool("codex")
    if not codex:
        print("  codex CLI: MISSING")
        print("    Install Codex first, then rerun bootstrap.")
        return 1

    print(f"  codex CLI: OK {codex}")
    try:
        completed = subprocess.run(
            [codex, "mcp", "get", "paper_search"],
            cwd=str(REPO_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        print("  codex mcp get paper_search: MISSING timed out")
        print("    Try a new terminal/session after trusting this repository.")
        return 1
    except Exception as exc:
        print(f"  codex mcp get paper_search: MISSING {exc}")
        return 1

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        print("  codex mcp get paper_search: MISSING")
        if output.strip():
            print("    " + output.strip().splitlines()[0])
        print("    Make sure the repo is trusted, then restart Codex or open a new session.")
        return 1

    checks = {
        "enabled: true": "enabled",
        "command: uv": "command",
        "args: run --frozen -m paper_search_mcp.server": "args",
        "cwd: EXTERNAL/paper-search-mcp": "cwd",
        "PAPER_SEARCH_MCP_ENV_FILE": "env file",
    }
    missing = [label for needle, label in checks.items() if needle not in output]
    if missing:
        print(f"  codex mcp get paper_search: MISSING fields {', '.join(missing)}")
        print("    Project config may not be loaded. Trust the repo and restart Codex/new session.")
        return 1

    print("  codex mcp get paper_search: OK")
    return 0

def load_toml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        import tomllib
    except Exception:
        return None, "tomllib unavailable; use Python 3.11+ for TOML validation"
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        return None, str(exc)
    return data, None

def check_project_codex_config() -> int:
    print("\nCodex project config")
    status = 0
    config_path = REPO_ROOT / ".codex" / "config.toml"
    if not config_path.is_file():
        print(f"  .codex/config.toml: MISSING")
        print_codex_config_help()
        return 1
    print(f"  .codex/config.toml: OK")

    data, error = load_toml(config_path)
    if error or data is None:
        print(f"  TOML parse: MISSING {error}")
        print_codex_config_help()
        return 1
    print("  TOML parse: OK")

    servers = data.get("mcp_servers", {})
    paper = servers.get("paper_search") if isinstance(servers, dict) else None
    if not isinstance(paper, dict):
        print("  mcp_servers.paper_search: MISSING")
        print_codex_config_help()
        return 1
    print("  mcp_servers.paper_search: OK")

    command = paper.get("command")
    args = paper.get("args")
    cwd_value = paper.get("cwd")
    enabled = paper.get("enabled")
    required = paper.get("required")

    if enabled is True:
        print("  enabled: OK true")
    else:
        print("  enabled: MISSING expected true")
        status = 1

    if required is False:
        print("  required: OK false")
    else:
        print("  required: MISSING expected false")
        status = 1

    if command == "uv":
        print("  command: OK uv")
    else:
        print(f"  command: MISSING expected uv, got {command!r}")
        status = 1

    if args == EXPECTED_PAPER_SEARCH_ARGS:
        print("  args: OK")
    else:
        print(f"  args: MISSING expected {EXPECTED_PAPER_SEARCH_ARGS}")
        status = 1

    cwd_path = repo_path(cwd_value) if cwd_value else None
    if cwd_path and cwd_path.is_dir():
        print(f"  cwd: OK {cwd_path}")
        if cwd_path.resolve() != EXPECTED_PAPER_SEARCH_CWD.resolve():
            print(f"  cwd target: MISSING expected {EXPECTED_PAPER_SEARCH_CWD}")
            status = 1
    else:
        print(f"  cwd: MISSING {cwd_path or '<unset>'}")
        status = 1

    status = max(status, check_optional_int("startup_timeout_sec", paper.get("startup_timeout_sec")))
    status = max(status, check_optional_int("tool_timeout_sec", paper.get("tool_timeout_sec")))

    approval_mode = paper.get("default_tools_approval_mode")
    if approval_mode == "auto":
        print("  default_tools_approval_mode: OK auto")
    else:
        print(f"  default_tools_approval_mode: MISSING expected auto, got {approval_mode!r}")
        status = 1

    if "env_vars" in paper:
        print("  env_vars: MISSING omit env_vars; use PAPER_SEARCH_MCP_ENV_FILE instead")
        status = 1
    else:
        print("  env_vars: OK omitted")

    env_table = paper.get("env", {})
    if not isinstance(env_table, dict):
        print("  env table: MISSING expected mapping")
        status = 1
        env_table = {}
    else:
        print("  env table: OK")

    env_file = env_table.get("PAPER_SEARCH_MCP_ENV_FILE") if isinstance(env_table, dict) else None
    if env_file == EXPECTED_PAPER_SEARCH_ENV_FILE:
        env_path = (cwd_path / str(env_file)).resolve() if cwd_path else Path(str(env_file))
        if env_path.is_file():
            print(f"  PAPER_SEARCH_MCP_ENV_FILE: OK {env_path}")
            if env_path.resolve() != DEPENDENCY_ENV.resolve():
                print(f"  env file target: MISSING expected {DEPENDENCY_ENV}")
                status = 1
        else:
            print(f"  PAPER_SEARCH_MCP_ENV_FILE: MISSING {env_path}")
            status = 1
    else:
        print(f"  PAPER_SEARCH_MCP_ENV_FILE: MISSING expected {EXPECTED_PAPER_SEARCH_ENV_FILE}")
        status = 1

    text = config_path.read_text(encoding="utf-8")
    if has_literal_secret(text):
        print("  secret scan: MISSING possible literal API key in config")
        status = 1
    else:
        print("  secret scan: OK no obvious literal API key")

    status = max(status, check_paper_search_files())
    status = max(status, check_codex_cli_mcp_visibility())
    return status

def check_secret_readiness() -> int:
    print("\nSecrets and API keys")
    status = 0
    print(f"  DEPENDENCY/.env.example: {'OK' if ENV_EXAMPLE.is_file() else 'MISSING'}")
    if not ENV_EXAMPLE.is_file():
        status = 1
    print(f"  DEPENDENCY/.env: {'OK' if DEPENDENCY_ENV.is_file() else 'MISSING'}")
    if LEGACY_ROOT_ENV.is_file():
        print("  repo .env: OK legacy fallback")
    else:
        print("  repo .env: MISSING optional legacy fallback")

    values = merged_env_values()
    openai_present = bool(values.get("OPENAI_API_KEY"))
    status = max(status, env_status("OPENAI_API_KEY", openai_present, required=True))
    if not openai_present:
        print_api_key_help("OPENAI_API_KEY")

    mp_present = bool(values.get("MP_API_KEY") or values.get("PMG_MAPI_KEY"))
    status = max(status, env_status("MP_API_KEY or PMG_MAPI_KEY", mp_present, required=True))
    if not mp_present:
        print_api_key_help("MP_API_KEY")

    hf_present = bool(values.get("HF_TOKEN"))
    print(f"  HF_TOKEN: {'SET' if hf_present else 'MISSING'} optional; needed for gated/private Hugging Face checkpoints")
    if not hf_present:
        print_api_key_help("HF_TOKEN")

    hf_home_present = bool(values.get("HF_HOME"))
    print(f"  HF_HOME: {'SET' if hf_home_present else 'MISSING'} optional; controls Hugging Face token/cache location")

    optional = [
        "OPENAI_MODEL",
        "OPENAI_EMBEDDING_KEY",
        "HF_TOKEN",
        "HF_HOME",
        "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL",
        "PAPER_SEARCH_MCP_CORE_API_KEY",
        "PAPER_SEARCH_MCP_SEMANTIC_SCHOLAR_API_KEY",
    ]
    set_count = sum(1 for key in optional if values.get(key))
    print(f"  useful optional keys: {set_count}/{len(optional)} set")
    return status

def check_platform() -> int:
    print("\nPlatform")
    system = platform.system()
    labels = {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}
    label = labels.get(system, system or "unknown")
    if system in labels:
        print(f"  operating system: OK {label}")
        return 0
    print(f"  operating system: MISSING unsupported {label}")
    print("  supported operating systems: Linux, macOS, Windows")
    return 1

def check_bootstrap_tools() -> int:
    print("\nBootstrap tools")
    status = 0
    required = ["uv"]
    optional = ["python", "qsub"]
    for tool in required:
        found = find_tool(tool)
        detail = f" ({Path(found).name})" if found else ""
        print(f"  {tool}: {'OK' if found else 'MISSING'}{detail}")
        if not found:
            status = 1
    for tool in optional:
        found = find_tool(tool)
        detail = f" ({Path(found).name})" if found else ""
        if tool == "python":
            note = " optional; uv can provide Python"
        else:
            note = " optional until needed"
        print(f"  {tool}: {'OK' if found else 'MISSING'}{detail}{note}")
    return status

def micromamba_platform_id() -> str | None:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Linux":
        if machine in {"x86_64", "amd64"}:
            return "linux-64"
        if machine in {"aarch64", "arm64"}:
            return "linux-aarch64"
        if machine == "ppc64le":
            return "linux-ppc64le"
    if system == "Darwin":
        if machine in {"x86_64", "amd64"}:
            return "osx-64"
        if machine in {"aarch64", "arm64"}:
            return "osx-arm64"
    if system == "Windows":
        if machine in {"amd64", "x86_64"}:
            return "win-64"
    return None

def write_mamba_wrapper(micromamba_path: Path) -> None:
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    try:
        is_local_micromamba = micromamba_path.resolve() == LOCAL_MICROMAMBA.resolve()
    except Exception:
        is_local_micromamba = False
    if platform.system() == "Windows":
        target = "%~dp0micromamba.exe" if is_local_micromamba else str(micromamba_path)
        wrapper = (
            "@echo off\r\n"
            'if "%MAMBA_ROOT_PREFIX%"=="" set "MAMBA_ROOT_PREFIX=%~dp0..\\.micromamba"\r\n'
            f'"{target}" %*\r\n'
        )
        LOCAL_MAMBA.write_text(wrapper, encoding="utf-8", newline="")
        return

    target = "$DIR/micromamba" if is_local_micromamba else str(micromamba_path)
    wrapper = (
        "#!/usr/bin/env sh\n"
        'DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        ': "${MAMBA_ROOT_PREFIX:=$DIR/../.micromamba}"\n'
        "export MAMBA_ROOT_PREFIX\n"
        f'exec "{target}" "$@"\n'
    )
    LOCAL_MAMBA.write_text(wrapper, encoding="utf-8")
    LOCAL_MAMBA.chmod(0o755)

def install_local_micromamba() -> int:
    platform_id = micromamba_platform_id()
    if not platform_id:
        print(f"  micromamba installer: MISSING unsupported platform {platform.system()} {platform.machine()}")
        return 1

    archive_url = f"https://micro.mamba.pm/api/micromamba/{platform_id}/latest"
    print(f"  micromamba download: {archive_url}")
    try:
        with urllib.request.urlopen(archive_url, timeout=120) as response:
            archive_bytes = response.read()
    except Exception as exc:
        print(f"  micromamba download: MISSING {exc}")
        return 1

    member_names = (
        ["Library/bin/micromamba.exe", "micromamba.exe"]
        if platform.system() == "Windows"
        else ["bin/micromamba", "micromamba"]
    )
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
            members = {member.name: member for member in archive.getmembers()}
            member = next((members[name] for name in member_names if name in members), None)
            if member is None:
                suffix = "/Library/bin/micromamba.exe" if platform.system() == "Windows" else "/bin/micromamba"
                member = next((candidate for candidate in members.values() if candidate.name.endswith(suffix)), None)
            if member is None:
                print(f"  micromamba archive: MISSING executable for {platform_id}")
                return 1
            extracted = archive.extractfile(member)
            if extracted is None:
                print(f"  micromamba archive: MISSING executable payload for {platform_id}")
                return 1
            payload = extracted.read()
    except Exception as exc:
        print(f"  micromamba archive: MISSING could not read archive: {exc}")
        return 1

    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    LOCAL_MICROMAMBA.write_bytes(payload)
    if platform.system() != "Windows":
        LOCAL_MICROMAMBA.chmod(0o755)
    write_mamba_wrapper(LOCAL_MICROMAMBA)
    print(f"  micromamba installed: OK {LOCAL_MICROMAMBA}")
    print(f"  mamba wrapper: OK {LOCAL_MAMBA}")
    print(f"  MAMBA_ROOT_PREFIX: {MAMBA_ROOT_PREFIX}")
    return 0

def conda_manager_version(path: str) -> str | None:
    try:
        completed = subprocess.run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            env=mesa_command_env(),
        )
    except Exception:
        return None
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode == 0 and output:
        return output.splitlines()[0]
    return None

def find_conda_manager() -> tuple[str, str] | None:
    for tool in ("mamba", "micromamba"):
        found = find_tool(tool)
        if found:
            return tool, found
    return None

def print_mamba_install_help() -> None:
    print("    Install repo-local micromamba and a mamba wrapper:")
    print("      bash DEPENDENCY/bootstrap.sh --install-mamba")
    print("      powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1 -InstallMamba")
    print("    Direct checker form:")
    print("      uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba")

def print_core_install_help() -> None:
    print("    Dry-run the core dependency recipe:")
    print("      bash DEPENDENCY/bootstrap.sh --install-core")
    print("    Execute the core dependency recipe after installing mamba:")
    print("      bash DEPENDENCY/bootstrap.sh --install-mamba --install-core --yes")
    print("    Windows PowerShell:")
    print("      powershell -ExecutionPolicy Bypass -File DEPENDENCY/bootstrap.ps1 -InstallMamba -InstallCore -Yes")
    print("    Direct checker form:")
    print("      uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py bootstrap --install-mamba --install-core --yes")

def check_conda_manager(install: bool) -> int:
    print("\nConda/mamba manager")
    manager = find_conda_manager()
    if manager:
        name, path = manager
        print(f"  {name}: OK {path}")
        version = conda_manager_version(path)
        if version:
            print(f"  version: OK {version}")
        if find_tool("mamba"):
            print("  mamba command: OK")
        elif install:
            print("  mamba command: MISSING; creating repo-local wrapper")
            write_mamba_wrapper(Path(path))
            print(f"  mamba wrapper: OK {LOCAL_MAMBA}")
        else:
            print("  mamba command: MISSING runtime install commands expect `mamba`")
            print_mamba_install_help()
        return 0

    conda = shutil.which("conda")
    if conda:
        print(f"  conda: OK {conda}")
        print("  mamba/micromamba: MISSING; mamba is preferred for this repo's conda-env runtimes")
    else:
        print("  mamba/micromamba: MISSING")

    if not install:
        print_mamba_install_help()
        return 0

    return install_local_micromamba()
