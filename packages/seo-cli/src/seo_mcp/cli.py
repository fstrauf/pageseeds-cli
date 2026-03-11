"""Plain Python CLI for seo-mcp (no MCP server).

This wraps the same underlying functions exposed as MCP tools in `seo_mcp.server`.

Examples:
  uv run --directory packages/seo-cli seo-cli keyword-generator --keyword "coffee beans" --country us
  uv run --directory packages/seo-cli seo-cli keyword-difficulty --keyword "expense tracker" --country us
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .secrets import load_capsolver_api_key


def _print_json(data: object) -> None:
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")

def _print_flat(keywords: list[str]) -> None:
    """Print one keyword per line (suitable for piping to other CLIs)."""
    for kw in keywords:
        sys.stdout.write(kw + "\n")


def _extract_keyword_strings(data: dict) -> list[str]:
    """Extract unique keyword strings from keyword-generator JSON output."""
    seen: set[str] = set()
    result: list[str] = []
    for key in ("all", "ideas", "questionIdeas"):
        for item in data.get(key, []):
            kw = item.get("keyword", "") if isinstance(item, dict) else str(item)
            if kw and kw not in seen:
                seen.add(kw)
                result.append(kw)
    return result


def _cmd_keyword_generator(args: argparse.Namespace) -> None:
    from seo_mcp.server import _keyword_generator

    result = _keyword_generator(keyword=args.keyword, country=args.country, search_engine=args.search_engine)
    if getattr(args, "output_format", "json") == "flat":
        _print_flat(_extract_keyword_strings(result))
    else:
        _print_json(result)


def _cmd_batch_keyword_generator(args: argparse.Namespace) -> None:
    """Run keyword-generator for multiple themes and output combined results."""
    from seo_mcp.server import _keyword_generator

    themes: list[str] = []
    if args.themes:
        themes.extend(args.themes)
    if args.themes_file:
        path = args.themes_file
        if path == "-":
            text = sys.stdin.read()
        else:
            text = Path(path).read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                themes.append(line)

    if not themes:
        sys.stderr.write("Error: no themes provided. Use --themes or --themes-file.\n")
        raise SystemExit(1)

    all_keywords: list[str] = []
    seen: set[str] = set()
    per_theme: list[dict] = []

    for theme in themes:
        sys.stderr.write(f"[keyword-generator] theme: {theme}\n")
        sys.stderr.flush()
        result = _keyword_generator(keyword=theme, country=args.country, search_engine=args.search_engine)
        kws = _extract_keyword_strings(result)
        new_kws = [k for k in kws if k not in seen]
        seen.update(new_kws)
        all_keywords.extend(new_kws)
        per_theme.append({"theme": theme, "keywords_found": len(kws), "new_unique": len(new_kws), "error": result.get("error")})

    if getattr(args, "output_format", "json") == "flat":
        _print_flat(all_keywords)
    else:
        _print_json({
            "themes_processed": len(themes),
            "total_unique_keywords": len(all_keywords),
            "per_theme": per_theme,
            "keywords": all_keywords,
        })


def _cmd_extract_keywords(args: argparse.Namespace) -> None:
    """Read keyword-generator JSON from stdin or file and output keyword strings."""
    if args.input_file and args.input_file != "-":
        text = Path(args.input_file).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    data = json.loads(text)
    keywords = _extract_keyword_strings(data)
    if getattr(args, "output_format", "json") == "flat":
        _print_flat(keywords)
    else:
        _print_json({"keywords": keywords, "count": len(keywords)})


def _cmd_keyword_difficulty(args: argparse.Namespace) -> None:
    from seo_mcp.server import _keyword_difficulty

    _print_json(_keyword_difficulty(keyword=args.keyword, country=args.country))


def _cmd_batch_keyword_difficulty(args: argparse.Namespace) -> None:
    from seo_mcp.server import _batch_keyword_difficulty

    keywords = []
    if args.keywords:
        keywords.extend(args.keywords)
    if args.keywords_file:
        if args.keywords_file == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.keywords_file).read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line:
                keywords.append(line)
    _print_json(_batch_keyword_difficulty(keywords=keywords, country=args.country))


def _cmd_backlinks(args: argparse.Namespace) -> None:
    from seo_mcp.server import _get_backlinks_list

    _print_json(_get_backlinks_list(domain=args.domain))


def _cmd_traffic(args: argparse.Namespace) -> None:
    from seo_mcp.server import _get_traffic

    _print_json(_get_traffic(domain_or_url=args.domain_or_url, country=args.country, mode=args.mode))


def _cmd_version(args: argparse.Namespace) -> None:
    from . import version_check
    version_check.print_version_check("seo-cli", "seo-mcp")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="seo-cli", description="SEO research operations without MCP")
    sp = p.add_subparsers(dest="cmd", required=True)

    kg = sp.add_parser("keyword-generator", help="Generate keyword ideas for a single theme")
    kg.add_argument("--keyword", required=True)
    kg.add_argument("--country", default="us")
    kg.add_argument("--search-engine", default="Google")
    kg.add_argument("--output-format", choices=["json", "flat"], default="json",
                     help="json (default) or flat (one keyword per line, pipeable)")
    kg.set_defaults(func=_cmd_keyword_generator)

    bkg = sp.add_parser("batch-keyword-generator", help="Generate keyword ideas for multiple themes at once")
    bkg.add_argument("--themes", nargs="*", default=[], help="Theme keywords")
    bkg.add_argument("--themes-file", default=None,
                     help="File with one theme per line (use '-' for stdin)")
    bkg.add_argument("--country", default="us")
    bkg.add_argument("--search-engine", default="Google")
    bkg.add_argument("--output-format", choices=["json", "flat"], default="json",
                     help="json (default) or flat (one keyword per line, pipeable)")
    bkg.set_defaults(func=_cmd_batch_keyword_generator)

    ek = sp.add_parser("extract-keywords", help="Extract keyword strings from keyword-generator JSON")
    ek.add_argument("--input-file", default="-",
                    help="Path to JSON file from keyword-generator (use '-' for stdin, default)")
    ek.add_argument("--output-format", choices=["json", "flat"], default="flat",
                    help="json or flat (default, one keyword per line)")
    ek.set_defaults(func=_cmd_extract_keywords)

    kd = sp.add_parser("keyword-difficulty", help="Analyze keyword difficulty and SERP")
    kd.add_argument("--keyword", required=True)
    kd.add_argument("--country", default="us")
    kd.set_defaults(func=_cmd_keyword_difficulty)

    bkd = sp.add_parser("batch-keyword-difficulty", help="Batch keyword difficulty")
    bkd.add_argument("--country", default="us")
    bkd.add_argument("--keywords", nargs="*", default=[])
    bkd.add_argument("--keywords-file", default=None,
                     help="One keyword per line (use '-' for stdin)")
    bkd.set_defaults(func=_cmd_batch_keyword_difficulty)

    bl = sp.add_parser("backlinks", help="Backlinks list")
    bl.add_argument("--domain", required=True)
    bl.set_defaults(func=_cmd_backlinks)

    tr = sp.add_parser("traffic", help="Traffic estimates")
    tr.add_argument("--domain-or-url", required=True)
    tr.add_argument("--country", default="None")
    tr.add_argument("--mode", choices=["subdomains", "exact"], default="subdomains")
    tr.set_defaults(func=_cmd_traffic)

    ver = sp.add_parser("version", help="Check CLI version and available updates")
    ver.set_defaults(func=_cmd_version)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        load_capsolver_api_key()
        args.func(args)
    except Exception as e:
        _print_json({"error": str(e), "type": e.__class__.__name__})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
