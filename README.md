# Changelogger

Generate release notes between two GitHub tags without depending on the `gh` CLI.

- Python 3.14 managed by `uv`
- CLI built with `cyclopts`
- Uses GitHub’s REST API (reads `GITHUB_TOKEN`)

## Setup (with uv)

```bash
# Install Python 3.14 into a repo-local location (avoids global writes)
uv python install 3.14 --install-dir .uv-python

# Create the virtualenv and install deps
UV_CACHE_DIR=.uv-cache UV_PYTHON=.uv-python/cpython-3.14.0-macos-aarch64-none/bin/python3.14 uv sync
# (adjust the interpreter path above to match the directory uv creates on your platform)
```

## Usage

Run directly with uv (no activation needed):

```bash
GITHUB_TOKEN=ghp_xxx uv run changelogger \
  --owner openai \
  --repo openai-python \
  --start-tag v1.86.0 \
  --end-tag v2.6.0 \
  --out releases_v1.86.0..v2.6.0.md
```

Or rely on the default config file:

```bash
# .changelogger.toml is read automatically if present
uv run changelogger
```

Flags:

- `--owner` / `--repo` – GitHub repository coordinates.
- `--start-tag` / `--end-tag` – oldest/newest tags delimiting the range.
- `--out` – path to the markdown file to write.
- `--config` – optional path to a TOML config (defaults to `.changelogger.toml`).
- `--include-prereleases` (default: true) / `--include-drafts` (default: false).

## Config file example

`.changelogger.toml` (auto-discovered):

```toml
owner = "openai"
repo = "openai-python"
start_tag = "v1.86.0"
end_tag = "v2.6.0"
out = "releases_v1.86.0..v2.6.0.md"
```

CLI flags override environment variables (`CHANGELOGGER_*`, `GITHUB_TOKEN`), which in turn override config values.
