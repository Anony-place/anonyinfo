from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import database
from anonyinfo_core.dossier import CaseBuilder
from anonyinfo_core.modules import build_default_registry
from anonyinfo_core.orchestrator import InvestigationOrchestrator, dumps_case_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AnonyInfo CLI-first investigation suite")
    subparsers = parser.add_subparsers(dest="command")

    investigate = subparsers.add_parser("investigate", help="Run a new investigation")
    investigate.add_argument("target_input", help="Seed input for investigation")
    investigate.add_argument("--full", action="store_true", help="Show expanded console output")
    investigate.add_argument("--format", choices=["console", "json", "html"], default="console", help="Output format")
    investigate.add_argument("--modules", help="Comma-separated module names to run")
    investigate.add_argument("--depth", choices=["standard", "deep"], default="standard", help="Investigation depth")
    investigate.add_argument("--nocache", action="store_true", help="Bypass per-module cache")
    investigate.add_argument("--output", help="Write JSON or HTML dossier to a file")
    investigate.add_argument("--report", action="store_true", help="Alias that writes JSON dossier to disk")

    case_parser = subparsers.add_parser("case", help="Read previously saved cases")
    case_subparsers = case_parser.add_subparsers(dest="case_command")
    show = case_subparsers.add_parser("show", help="Show a saved case")
    show.add_argument("case_id")
    show.add_argument("--format", choices=["console", "json", "html"], default="console")
    show.add_argument("--full", action="store_true")
    export = case_subparsers.add_parser("export", help="Export a saved case")
    export.add_argument("case_id")
    export.add_argument("--format", choices=["json", "html", "csv"], default="json")
    export.add_argument("--output", help="Destination file path")

    return parser


def parse_args():
    if len(sys.argv) > 1 and sys.argv[1] not in {"investigate", "case", "-h", "--help"}:
        legacy_parser = argparse.ArgumentParser(description="AnonyInfo legacy compatibility mode")
        legacy_parser.add_argument("target_input")
        legacy_parser.add_argument("--report", action="store_true")
        legacy_parser.add_argument("--nocache", action="store_true")
        args = legacy_parser.parse_args()
        args.command = "investigate"
        args.full = False
        args.format = "console"
        args.modules = None
        args.depth = "standard"
        args.output = None
        return args

    parser = build_parser()
    args = parser.parse_args()
    return args


def selected_modules(raw: str | None):
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


async def run_investigation(args):
    database.init_db()
    registry = build_default_registry()
    orchestrator = InvestigationOrchestrator(registry, database)
    _, dossier = await orchestrator.investigate(
        args.target_input,
        depth=args.depth,
        selected_modules=selected_modules(args.modules),
        use_cache=not args.nocache,
    )
    builder = CaseBuilder()
    rendered = render_dossier(builder, dossier, args.format, args.full)
    output_path = None
    if args.report and not args.output:
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in args.target_input)
        args.output = f"ANONYINFO_CASE_{safe_name}.json"
        args.format = "json"
        rendered = render_dossier(builder, dossier, args.format, args.full)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(rendered, encoding="utf-8")
    return rendered, output_path


def render_dossier(builder: CaseBuilder, dossier: dict, output_format: str, full: bool):
    if output_format == "json":
        return dumps_case_json(dossier)
    if output_format == "html":
        return builder.render_html(dossier)
    return builder.render_console(dossier, full=full)


def export_case(case_id: str, export_format: str, output: str | None):
    case_record = database.get_case(case_id)
    if not case_record:
        raise SystemExit(f"Case not found: {case_id}")
    builder = CaseBuilder()
    dossier = builder.build(case_record)

    if export_format == "csv":
        lines = ["module,title,summary,entity_type,entity_value,confidence"]
        for finding in dossier["evidence_table"]:
            row = [
                finding["module"],
                finding["title"].replace(",", " "),
                finding["summary"].replace(",", " "),
                finding["entity_type"],
                finding["entity_value"].replace(",", " "),
                str(finding["confidence"]),
            ]
            lines.append(",".join(row))
        rendered = "\n".join(lines)
    else:
        rendered = render_dossier(builder, dossier, export_format, full=True)

    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    return rendered


def show_case(case_id: str, output_format: str, full: bool):
    case_record = database.get_case(case_id)
    if not case_record:
        raise SystemExit(f"Case not found: {case_id}")
    builder = CaseBuilder()
    dossier = builder.build(case_record)
    return render_dossier(builder, dossier, output_format, full)


def main():
    args = parse_args()
    if args.command == "investigate":
        rendered, output_path = asyncio.run(run_investigation(args))
        print(rendered)
        if output_path:
            print(f"\nSaved dossier to {output_path}")
        return

    if args.command == "case" and args.case_command == "show":
        print(show_case(args.case_id, args.format, args.full))
        return

    if args.command == "case" and args.case_command == "export":
        print(export_case(args.case_id, args.format, args.output))
        return

    build_parser().print_help()


if __name__ == "__main__":
    main()
