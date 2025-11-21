from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Dict, List, Tuple

import httpx
import tomllib
from cyclopts import App, Parameter

API_BASE = "https://api.github.com"
DEFAULT_CONFIG_PATH = Path(".changelogger.toml")
ENV_PREFIX = "CHANGELOGGER_"

app = App(help="Generate GitHub release notes between two tags.")


@dataclass
class Settings:
    owner: str
    repo: str
    start_tag: str
    end_tag: str
    out: Path
    token: str | None
    include_prereleases: bool
    include_drafts: bool


def _load_config(config_path: Path | None) -> Dict[str, Any]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Config file {config_path} not found.")
    with config_path.open("rb") as fh:
        data = tomllib.load(fh)
    return {key.replace("-", "_"): value for key, value in data.items()}


def _pick(
    name: str,
    cli_value: Any,
    config: Dict[str, Any],
) -> Any:
    env_value = os.getenv(f"{ENV_PREFIX}{name.upper()}")
    return cli_value or env_value or config.get(name)


def _resolve_settings(
    *,
    owner: str | None,
    repo: str | None,
    start_tag: str | None,
    end_tag: str | None,
    out: Path | None,
    config_path: Path | None,
    token: str | None,
    include_prereleases: bool,
    include_drafts: bool,
) -> Settings:
    derived_config_path = config_path or (DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else None)
    config = _load_config(derived_config_path)

    owner_val = _pick("owner", owner, config)
    repo_val = _pick("repo", repo, config)
    start_val = _pick("start_tag", start_tag, config)
    end_val = _pick("end_tag", end_tag, config)
    out_val = _pick("out", str(out) if out else None, config)
    token_val = token or os.getenv("GITHUB_TOKEN") or config.get("token")

    missing = [
        name
        for name, value in [
            ("owner", owner_val),
            ("repo", repo_val),
            ("start-tag", start_val),
            ("end-tag", end_val),
            ("out", out_val),
        ]
        if value in (None, "")
    ]
    if missing:
        raise ValueError(
            "Missing required values: "
            + ", ".join(missing)
            + ". Provide them via flags, environment variables, or a config file."
        )

    return Settings(
        owner=owner_val,
        repo=repo_val,
        start_tag=start_val,
        end_tag=end_val,
        out=Path(out_val),
        token=token_val,
        include_prereleases=include_prereleases,
        include_drafts=include_drafts,
    )


def _github_client(token: str | None) -> httpx.Client:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "changelogger/0.1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(headers=headers, timeout=30.0, follow_redirects=True)


def _fetch_releases_between_tags(settings: Settings) -> Tuple[List[Dict[str, Any]], bool, bool]:
    url = f"{API_BASE}/repos/{settings.owner}/{settings.repo}/releases"
    page = 1
    collecting = False
    found_start = False
    found_end = False
    releases: List[Dict[str, Any]] = []

    with _github_client(settings.token) as client:
        while True:
            response = client.get(url, params={"per_page": 100, "page": page})
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break

            for release in batch:
                tag = release.get("tag_name")
                if tag == settings.end_tag:
                    collecting = True
                    found_end = True
                if collecting:
                    if (settings.include_drafts or not release.get("draft", False)) and (
                        settings.include_prereleases or not release.get("prerelease", False)
                    ):
                        releases.append(release)
                if tag == settings.start_tag:
                    found_start = True
                    return releases, found_start, found_end
            page += 1

    return releases, found_start, found_end


def _render_release(release: Dict[str, Any]) -> str:
    tag = release.get("tag_name", "unknown-tag")
    published_at = release.get("published_at") or ""
    body = release.get("body") or ""
    return f"## {tag}\n{tag} ({published_at})\n{body}\n\n"


def _write_output(out_path: Path, releases: List[Dict[str, Any]]) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(_render_release(release) for release in releases)
    out_path.write_text(rendered, encoding="utf-8")
    return len(rendered.splitlines())


@app.default
def main(
    *,
    owner: Annotated[str | None, Parameter(required=False, help="GitHub owner/organization.")] = None,
    repo: Annotated[str | None, Parameter(required=False, help="GitHub repository name.")] = None,
    start_tag: Annotated[
        str | None, Parameter(name="start-tag", required=False, help="Oldest tag in range.")
    ] = None,
    end_tag: Annotated[
        str | None, Parameter(name="end-tag", required=False, help="Newest tag in range.")
    ] = None,
    out: Annotated[
        Path | None, Parameter(required=False, converter=Path, help="Output markdown path.")
    ] = None,
    config: Annotated[
        Path | None,
        Parameter(
            required=False,
            converter=Path,
            help="Path to a TOML config file. Defaults to .changelogger.toml if present.",
        ),
    ] = None,
    token: Annotated[
        str | None,
        Parameter(
            required=False,
            env_var="GITHUB_TOKEN",
            show_default=False,
            help="GitHub token. Falls back to the GITHUB_TOKEN environment variable.",
        ),
    ] = None,
    include_prereleases: Annotated[
        bool, Parameter(help="Include prereleases in the range (matches gh behavior).")
    ] = True,
    include_drafts: Annotated[bool, Parameter(help="Include draft releases.")] = False,
) -> None:
    """
    Write release notes for releases between --end-tag (newest) and --start-tag (oldest) to --out.
    """
    try:
        settings = _resolve_settings(
            owner=owner,
            repo=repo,
            start_tag=start_tag,
            end_tag=end_tag,
            out=out,
            config_path=config,
            token=token,
            include_prereleases=include_prereleases,
            include_drafts=include_drafts,
        )

        releases, found_start, found_end = _fetch_releases_between_tags(settings)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(str(exc))
    except httpx.HTTPError as exc:
        detail = ""
        if exc.response is not None:
            detail = f" (HTTP {exc.response.status_code}: {exc.response.text})"
        raise SystemExit(f"GitHub API request failed{detail}") from exc

    if not found_end:
        raise SystemExit(f"End tag {settings.end_tag!r} was not found in the release list.")
    if not found_start:
        raise SystemExit(
            f"Start tag {settings.start_tag!r} was not found after {settings.end_tag!r}."
        )

    lines = _write_output(settings.out, releases)
    print(f"Wrote {len(releases)} releases ({lines} lines) to {settings.out}")


if __name__ == "__main__":
    app()
