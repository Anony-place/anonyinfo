from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import database
from anonyinfo_core.dossier import CaseBuilder
from anonyinfo_core.normalizer import InputNormalizer
from anonyinfo_core.modules import build_default_registry
from anonyinfo_core.orchestrator import InvestigationOrchestrator, dumps_case_json
from anonyinfo_core.scoring import ResultScorer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AnonyInfo CLI-first investigation suite")
    subparsers = parser.add_subparsers(dest="command")

    investigate = subparsers.add_parser("investigate", help="Run a new investigation")
    investigate.add_argument("target_input", help="Seed input for investigation")
    investigate.add_argument("--full", action="store_true", help="Show expanded console output")
    investigate.add_argument("--format", choices=["console", "json", "html", "graph"], default="console", help="Output format")
    investigate.add_argument("--modules", help="Comma-separated module names to run")
    investigate.add_argument("--depth", choices=["standard", "deep"], default="standard", help="Investigation depth")
    investigate.add_argument("--nocache", action="store_true", help="Bypass per-module cache")
    investigate.add_argument("--output", help="Write JSON or HTML dossier to a file")
    investigate.add_argument("--report", action="store_true", help="Alias that writes JSON dossier to disk")

    case_parser = subparsers.add_parser("case", help="Read previously saved cases")
    case_subparsers = case_parser.add_subparsers(dest="case_command")
    show = case_subparsers.add_parser("show", help="Show a saved case")
    show.add_argument("case_id")
    show.add_argument("--format", choices=["console", "json", "html", "graph"], default="console")
    show.add_argument("--full", action="store_true")
    export = case_subparsers.add_parser("export", help="Export a saved case")
    export.add_argument("case_id")
    export.add_argument("--format", choices=["json", "html", "csv", "graph"], default="json")
    export.add_argument("--output", help="Destination file path")
    compare = case_subparsers.add_parser("compare", help="Compare two saved cases")
    compare.add_argument("left_case_id")
    compare.add_argument("right_case_id")
    compare.add_argument("--format", choices=["console", "json"], default="console")
    rerun = case_subparsers.add_parser("rerun", help="Rerun an existing case")
    rerun.add_argument("case_id")
    rerun.add_argument("--modules", help="Comma-separated module names to rerun")
    rerun.add_argument("--depth", choices=["standard", "deep"], help="Override depth")
    rerun.add_argument("--format", choices=["console", "json", "html", "graph"], default="console")

    watch_parser = subparsers.add_parser("watch", help="Manage watch targets")
    watch_subparsers = watch_parser.add_subparsers(dest="watch_command")
    watch_add = watch_subparsers.add_parser("add", help="Add a watch target")
    watch_add.add_argument("target_input")
    watch_list = watch_subparsers.add_parser("list", help="List watch targets")

    note_parser = subparsers.add_parser("note", help="Manage case notes")
    note_subparsers = note_parser.add_subparsers(dest="note_command")
    note_add = note_subparsers.add_parser("add", help="Add a case note")
    note_add.add_argument("case_id")
    note_add.add_argument("note_text")
    note_add.add_argument("--entity-id")
    note_list = note_subparsers.add_parser("list", help="List notes for a case")
    note_list.add_argument("case_id")

    connector_parser = subparsers.add_parser("connector", help="Manage opt-in connectors")
    connector_subparsers = connector_parser.add_subparsers(dest="connector_command")
    connector_add = connector_subparsers.add_parser("add", help="Add a connector account")
    connector_add.add_argument("provider")
    connector_add.add_argument("--label", required=True)
    connector_add.add_argument("--config", default="{}", help="JSON config payload")
    connector_list = connector_subparsers.add_parser("list", help="List connector accounts")

    return parser


def parse_args():
    if len(sys.argv) > 1 and sys.argv[1] not in {"investigate", "case", "watch", "note", "connector", "-h", "--help"}:
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


async def rerun_case(args):
    database.init_db()
    original = database.get_case(args.case_id)
    if not original:
        raise SystemExit(f"Case not found: {args.case_id}")
    rerun_job = database.create_rerun_job(args.case_id, selected_modules(args.modules), args.depth or original.depth)
    registry = build_default_registry()
    orchestrator = InvestigationOrchestrator(registry, database)
    _, dossier = await orchestrator.investigate(
        original.target_input,
        depth=args.depth or original.depth,
        selected_modules=selected_modules(args.modules) or original.modules,
        use_cache=False,
    )
    database.complete_rerun_job(rerun_job["rerun_id"], dossier["case"]["id"])
    builder = CaseBuilder()
    return render_dossier(builder, dossier, args.format, full=True)


def render_dossier(builder: CaseBuilder, dossier: dict, output_format: str, full: bool):
    if output_format == "json":
        return dumps_case_json(dossier)
    if output_format == "html":
        return builder.render_html(dossier)
    if output_format == "graph":
        return builder.render_graph(dossier["graph"])
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


def compare_cases(left_case_id: str, right_case_id: str, output_format: str):
    left_case = database.get_case(left_case_id)
    right_case = database.get_case(right_case_id)
    if not left_case:
        raise SystemExit(f"Case not found: {left_case_id}")
    if not right_case:
        raise SystemExit(f"Case not found: {right_case_id}")
    comparison = ResultScorer().compare_cases(left_case, right_case)
    if output_format == "json":
        return dumps_case_json(comparison)
    lines = [
        f"Compare {comparison['left_case_id']} vs {comparison['right_case_id']}",
        f"Scores: left {comparison['left_score']} | right {comparison['right_score']}",
        "",
        f"Shared entities: {len(comparison['shared_entities'])}",
    ]
    lines.extend(f"- {item}" for item in comparison["shared_entities"][:12])
    lines.append("")
    lines.append(f"Left-only entities: {len(comparison['left_only_entities'])}")
    lines.extend(f"- {item}" for item in comparison["left_only_entities"][:12])
    lines.append("")
    lines.append(f"Right-only entities: {len(comparison['right_only_entities'])}")
    lines.extend(f"- {item}" for item in comparison["right_only_entities"][:12])
    lines.append("")
    lines.append(f"Shared modules: {', '.join(comparison['shared_modules']) if comparison['shared_modules'] else 'None'}")
    return "\n".join(lines)


def add_watch_target(target_input: str):
    entities = InputNormalizer().normalize(target_input)
    seed = entities[0]
    item = database.add_watch_target(target_input, seed.entity_type, seed.value)
    return f"Watch added: {item['watch_id']} -> {item['normalized_type']}:{item['normalized_value']}"


def list_watch_targets():
    rows = database.get_watch_targets()
    if not rows:
        return "No watch targets."
    return "\n".join(
        f"{row['watch_id']} | {row['normalized_type']}:{row['normalized_value']} | {row['status']} | last_case={row['last_case_id'] or '-'}"
        for row in rows
    )


def add_case_note(case_id: str, note_text: str, entity_id: str | None):
    note = database.add_case_note(case_id, note_text, entity_id=entity_id)
    return f"Note added: {note['note_id']} for {case_id}"


def list_case_notes(case_id: str):
    notes = database.get_case_notes(case_id)
    if not notes:
        return "No notes."
    return "\n".join(f"{item['created_at']} | {item['entity_id'] or '-'} | {item['note_text']}" for item in notes)


def add_connector(provider: str, label: str, config_raw: str):
    try:
        config = json.loads(config_raw)
    except json.JSONDecodeError as exc:
        if "=" in config_raw:
            config = {}
            for item in config_raw.split(","):
                if "=" not in item:
                    raise SystemExit(f"Invalid connector config JSON: {exc}")
                key, value = item.split("=", 1)
                config[key.strip()] = value.strip()
        else:
            raise SystemExit(f"Invalid connector config JSON: {exc}")
    item = database.add_connector_account(provider, label, config)
    return f"Connector added: {item['connector_id']} [{item['provider']}] {item['label']}"


def list_connectors():
    rows = database.get_connector_accounts()
    if not rows:
        return "No connectors configured."
    return "\n".join(
        f"{row['connector_id']} | {row['provider']} | {row['label']} | {row['status']}"
        for row in rows
    )


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

    if args.command == "case" and args.case_command == "compare":
        print(compare_cases(args.left_case_id, args.right_case_id, args.format))
        return

    if args.command == "case" and args.case_command == "rerun":
        print(asyncio.run(rerun_case(args)))
        return

    if args.command == "watch" and args.watch_command == "add":
        print(add_watch_target(args.target_input))
        return

    if args.command == "watch" and args.watch_command == "list":
        print(list_watch_targets())
        return

    if args.command == "note" and args.note_command == "add":
        print(add_case_note(args.case_id, args.note_text, args.entity_id))
        return

    if args.command == "note" and args.note_command == "list":
        print(list_case_notes(args.case_id))
        return

    if args.command == "connector" and args.connector_command == "add":
        print(add_connector(args.provider, args.label, args.config))
        return

    if args.command == "connector" and args.connector_command == "list":
        print(list_connectors())
        return

    build_parser().print_help()


if __name__ == "__main__":
    main()
