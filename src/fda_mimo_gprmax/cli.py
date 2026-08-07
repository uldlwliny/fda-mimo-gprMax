"""Command-line interface for FDA-MIMO-GPR gprMax compatibility layer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ValidationError, load_scenario
from .diagnostics import write_diagnostics
from .parsing import OutputParseError, parse_tx_outputs
from .processing import ProcessingError, make_snapshot
from .protocol import (
    analyze_protocol,
    execute_protocol_real_runs,
    plan_protocol,
    protocol_cache_status,
    report_protocol,
)
from .rendering import render_scenario_inputs
from .running import build_command_plan, run_plan, write_manifest
from .serialization import write_processed_snapshot
from .subtraction import SubtractionError, subtract_scene_run
from .inspection import inspect_run
from .validation import (
    ValidationSuiteError,
    gprmax_smoke_validation_case,
    run_synthetic_validation_suite,
    write_json,
    write_report,
    write_summary,
)


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_validate(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    _print_json(
        {
            "ok": True,
            "name": scenario.name,
            "nt": scenario.nt,
            "nr": scenario.nr,
            "checksum": scenario.checksum(),
        }
    )
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    variants = [args.variant] if args.variant else [v.name for v in scenario.variants]
    plans = []
    for variant in variants:
        plan = render_scenario_inputs(
            scenario, variant_name=variant, run_dir=args.run_dir
        )
        commands = [
            build_command_plan(scenario, plan, item, geometry_only=args.geometry_only)
            for item in plan.inputs
        ]
        write_manifest(plan, scenario, commands, stage="dry-run")
        plans.append(plan.to_manifest())
    _print_json({"ok": True, "plans": plans})
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    plan = render_scenario_inputs(
        scenario, variant_name=args.variant, run_dir=args.run_dir
    )
    if args.dry_run:
        commands = [
            build_command_plan(scenario, plan, item, geometry_only=args.geometry_only)
            for item in plan.inputs
        ]
        write_manifest(plan, scenario, commands, stage="dry-run")
        _print_json(
            {
                "ok": True,
                "dry_run": True,
                "commands": [cmd.to_dict() for cmd in commands],
            }
        )
        return 0
    results = run_plan(
        scenario, plan, geometry_only=args.geometry_only, timeout=args.timeout
    )
    _print_json(
        {"ok": all(r.ok for r in results), "results": [r.to_dict() for r in results]}
    )
    return 0 if all(r.ok for r in results) else 2


def cmd_process(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    raw_dir = (
        Path(args.raw_dir)
        if args.raw_dir
        else scenario.output_root
        / scenario.name
        / (args.variant or scenario.variants[0].name)
        / "raw"
    )
    out_dir = (
        Path(args.processed_dir) if args.processed_dir else raw_dir.parent / "processed"
    )
    paths = [raw_dir / f"tx_{i:03d}.out" for i in range(scenario.nt)]
    traces = parse_tx_outputs(
        paths, scenario.receiver.component, expected_nrx=scenario.nr
    )
    snapshot = make_snapshot(traces, scenario, normalize=not args.no_normalize)
    written = write_processed_snapshot(
        snapshot, out_dir, export_npz=scenario.processing.export_npz
    )
    diagnostics = {}
    if scenario.processing.diagnostics and not args.no_diagnostics:
        diagnostics = {
            k: str(v)
            for k, v in write_diagnostics(snapshot, raw_dir.parent / "figures").items()
        }
    _print_json(
        {
            "ok": True,
            "outputs": {k: str(v) for k, v in written.items()},
            "diagnostics": diagnostics,
        }
    )
    return 0


def cmd_protocol(args: argparse.Namespace) -> int:
    if args.action in {"plan", "run", "analyze"} and not args.scenario:
        raise ValidationError("protocol action requires a scenario YAML path")
    if args.action == "plan":
        payload = plan_protocol(
            args.scenario,
            args.output_root,
            checks=args.checks,
            overwrite=args.overwrite,
        )
        _print_json(payload)
        return 0
    if args.action == "analyze":
        suite = analyze_protocol(
            args.scenario,
            args.output_root,
            checks=args.checks,
            paper_mode=args.paper_mode,
            overwrite=args.overwrite,
        )
        _print_json(suite.to_dict())
        return 0 if suite.decision.accepted or args.allow_not_accepted else 2
    if args.action == "run":
        # Real full-wave execution is intentionally explicit. Without --execute-real,
        # run mode performs a resumable cache/status pass plus planning artifacts.
        if not args.execute_real:
            plan = plan_protocol(
                args.scenario,
                args.output_root,
                checks=args.checks,
                overwrite=args.overwrite,
            )
            payload = {
                "mode": "run",
                "execute_real": False,
                "message": "real gprMax execution skipped; pass --execute-real to opt in",
                "plan": plan,
                "cache": protocol_cache_status(args.output_root, args.checks),
            }
            _print_json(payload)
            return 0
        payload = execute_protocol_real_runs(
            args.scenario,
            args.output_root,
            checks=args.checks,
            timeout=args.timeout,
            force=args.overwrite,
        )
        _print_json(payload)
        ok = all(
            item.get("status") in {"complete", "cached"}
            for item in payload.get("results", [])
        )
        return 0 if ok or args.allow_not_accepted else 2
    if args.action == "report":
        suite = report_protocol(
            args.output_root, checks=args.checks, paper_mode=args.paper_mode
        )
        _print_json(suite.to_dict())
        return 0 if suite.decision.accepted or args.allow_not_accepted else 2
    raise ValueError(f"unknown protocol action: {args.action}")


def cmd_evidence(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    suite = run_synthetic_validation_suite(
        scenario,
        args.output_dir,
        tolerance=args.tolerance,
        overwrite=args.overwrite,
        write_report_file=not args.no_report,
    )
    smoke_result = None
    if args.include_smoke:
        smoke_result = gprmax_smoke_validation_case(
            scenario, suite.output_dir, timeout=args.timeout, tolerance=args.tolerance
        )
        results = (*suite.results, smoke_result)
        suite = type(suite)(
            suite.suite_name, suite.output_dir, results, artifacts=suite.artifacts
        )
        write_summary(suite)
        if not args.no_report:
            write_report(suite)
    payload = suite.to_dict()
    _print_json(payload)
    return 0 if suite.passed else 2


def cmd_workflow(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    variant = args.variant or scenario.variants[0].name
    workflow_run_dir = Path(args.run_dir) / variant if args.run_dir else None
    plan = render_scenario_inputs(
        scenario, variant_name=variant, run_dir=workflow_run_dir
    )
    commands = [
        build_command_plan(scenario, plan, item, geometry_only=args.geometry_only)
        for item in plan.inputs
    ]
    write_manifest(
        plan, scenario, commands, stage="dry-run" if args.dry_run else "planned"
    )
    if args.dry_run:
        _print_json(
            {
                "ok": True,
                "dry_run": True,
                "render_plan": plan.to_manifest(),
                "commands": [cmd.to_dict() for cmd in commands],
            }
        )
        return 0
    results = run_plan(
        scenario, plan, geometry_only=args.geometry_only, timeout=args.timeout
    )
    if not all(r.ok for r in results):
        _print_json(
            {"ok": False, "stage": "run", "results": [r.to_dict() for r in results]}
        )
        return 2
    if args.geometry_only:
        _print_json(
            {
                "ok": True,
                "geometry_only": True,
                "stage": "geometry",
                "results": [r.to_dict() for r in results],
                "run_dir": str(plan.run_dir),
            }
        )

        return 0
    traces = parse_tx_outputs(
        [item.output_path for item in plan.inputs],
        scenario.receiver.component,
        expected_nrx=scenario.nr,
    )
    snapshot = make_snapshot(traces, scenario, normalize=True)
    written = write_processed_snapshot(
        snapshot, plan.processed_dir, export_npz=scenario.processing.export_npz
    )
    diagnostics = (
        {k: str(v) for k, v in write_diagnostics(snapshot, plan.figures_dir).items()}
        if scenario.processing.diagnostics
        else {}
    )
    _print_json(
        {
            "ok": True,
            "outputs": {k: str(v) for k, v in written.items()},
            "diagnostics": diagnostics,
            "run_dir": str(plan.run_dir),
        }
    )
    return 0


def cmd_subtract(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    scene_root = (
        Path(args.run_dir) if args.run_dir else scenario.output_root / scenario.name
    )
    result = subtract_scene_run(
        scene_root,
        target_variant=args.target_variant,
        background_variant=args.background_variant,
    )
    _print_json({"ok": True, **result.to_dict()})
    return 0


def cmd_inspect_run(args: argparse.Namespace) -> int:
    variants = (
        [item.strip() for item in args.variants.split(",") if item.strip()]
        if args.variants
        else None
    )
    result = inspect_run(
        args.run_dir,
        variants=variants,
        with_scatter=args.with_scatter,
        paper_mode=args.paper_mode,
        output=args.output,
    )
    _print_json(
        {"ok": result.summary.get("decision") != "NOT_ACCEPTED", **result.to_dict()}
    )
    return (
        0
        if result.summary.get("decision") != "NOT_ACCEPTED" or args.allow_not_accepted
        else 2
    )


def cmd_protocol_real(args: argparse.Namespace) -> int:
    result = inspect_run(
        args.run_dir,
        variants=["target", "background"],
        with_scatter=args.with_scatter,
        paper_mode=True,
        output=args.output,
    )
    payload = {
        "ok": result.summary.get("decision") != "NOT_ACCEPTED",
        "type": "real-run",
        "decision": result.summary.get("decision"),
        "checks": result.summary.get("real_run_checks", {}),
        "summary": str(result.summary_path),
        "report": str(result.report_path),
        "note": "Real-run protocol checks currently evaluate V1-V4; V5-V8 remain not evaluated unless required real datasets exist.",
    }
    _print_json(payload)
    return 0 if payload["ok"] or args.allow_not_accepted else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fda-mimo-gprmax",
        description="TDM FDA-MIMO-GPR compatibility layer for gprMax",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate scenario YAML")
    p.add_argument("scenario")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("render", help="render gprMax input files without executing")
    p.add_argument("scenario")
    p.add_argument("--variant")
    p.add_argument("--run-dir")
    p.add_argument("--geometry-only", action="store_true")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("run", help="render and execute gprMax inputs")
    p.add_argument("scenario")
    p.add_argument("--variant")
    p.add_argument("--run-dir")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--geometry-only", action="store_true")
    p.add_argument("--timeout", type=float)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("process", help="process raw gprMax outputs into snapshots")
    p.add_argument("scenario")
    p.add_argument("--variant")
    p.add_argument("--raw-dir")
    p.add_argument("--processed-dir")
    p.add_argument("--no-normalize", action="store_true")
    p.add_argument("--no-diagnostics", action="store_true")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser(
        "protocol", help="run or plan first-stage theory validation protocol"
    )
    p.add_argument("action", choices=["plan", "run", "analyze", "report"])
    p.add_argument(
        "scenario", nargs="?", help="scenario YAML; required for plan/run/analyze"
    )
    p.add_argument("--output-root", default="output/protocol/latest")
    p.add_argument(
        "--checks", default="all", help="comma-separated check IDs, e.g. V1,V2,V3"
    )
    p.add_argument("--overwrite", action="store_true")
    p.add_argument(
        "--paper-mode",
        action="store_true",
        help="require enhanced evidence gate for reports/benchmark use",
    )
    p.add_argument(
        "--allow-not-accepted",
        action="store_true",
        help="exit zero even when first-stage gate is not accepted",
    )
    p.add_argument(
        "--execute-real",
        action="store_true",
        help="explicit opt-in for real gprMax protocol execution",
    )
    p.add_argument(
        "--timeout",
        type=float,
        help="reserved timeout for real gprMax protocol execution",
    )
    p.set_defaults(func=cmd_protocol)

    p = sub.add_parser(
        "evidence", help="run validation evidence suite and write report artifacts"
    )
    p.add_argument("scenario")
    p.add_argument("--output-dir", default="output/evidence/latest")
    p.add_argument("--tolerance", type=float, default=1e-6)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--no-report", action="store_true")
    p.add_argument(
        "--include-smoke",
        action="store_true",
        help="opt-in real gprMax smoke validation",
    )
    p.add_argument(
        "--timeout",
        type=float,
        help="timeout in seconds for optional smoke gprMax commands",
    )
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser(
        "workflow", help="end-to-end workflow; use --dry-run before executing gprMax"
    )
    p.add_argument("scenario")
    p.add_argument("--variant")
    p.add_argument(
        "--run-dir", help="scene run root; workflow writes <run-dir>/<variant>/"
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--geometry-only", action="store_true")
    p.add_argument("--timeout", type=float)
    p.set_defaults(func=cmd_workflow)

    p = sub.add_parser(
        "subtract", help="subtract background snapshot from target snapshot"
    )
    p.add_argument("scenario")
    p.add_argument(
        "--run-dir", help="scene run root containing target/ and background/"
    )
    p.add_argument("--target-variant", default="target")
    p.add_argument("--background-variant", default="background")
    p.set_defaults(func=cmd_subtract)

    p = sub.add_parser("inspect-run", help="inspect an existing scene run directory")
    p.add_argument("run_dir")
    p.add_argument(
        "--variants",
        help="comma-separated variants to inspect, default: target,background",
    )
    p.add_argument("--with-scatter", action="store_true")
    p.add_argument("--paper-mode", action="store_true")
    p.add_argument("--output")
    p.add_argument("--allow-not-accepted", action="store_true")
    p.set_defaults(func=cmd_inspect_run)

    p = sub.add_parser(
        "protocol-real", help="real-run V1-V4 protocol analysis from run products"
    )
    p.add_argument("run_dir")
    p.add_argument("--with-scatter", action="store_true")
    p.add_argument("--output")
    p.add_argument("--allow-not-accepted", action="store_true")
    p.set_defaults(func=cmd_protocol_real)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        ValidationError,
        OutputParseError,
        ProcessingError,
        ValidationSuiteError,
        SubtractionError,
        ValueError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
