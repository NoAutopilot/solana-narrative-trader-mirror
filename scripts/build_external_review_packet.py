#!/usr/bin/env python3
"""
build_external_review_packet.py — Assemble a clean project packet for external review.

Reads existing reports, configs, and status files to produce a self-contained
review packet in Markdown, YAML, and optionally JSON.

Usage:
  python3 scripts/build_external_review_packet.py \
      --output-dir reports/external_review/

  python3 scripts/build_external_review_packet.py --format yaml \
      --output-dir reports/external_review/
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# Packet sections — each reads from existing files or returns defaults
# ══════════════════════════════════════════════════════════════════════════════

def _read_file_safe(path: str) -> Optional[str]:
    """Read a file, return None if missing."""
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return None


def _find_project_root() -> str:
    """Find the project root by looking for .git directory."""
    d = Path(__file__).resolve().parent.parent
    if (d / ".git").exists():
        return str(d)
    return str(Path.cwd())


def section_project_goal(root: str) -> dict:
    """Project goal and scope."""
    return {
        "title": "Project Goal",
        "content": (
            "Build a systematic Solana memecoin trading system that identifies "
            "short-horizon alpha in newly launched tokens using microstructure, "
            "order flow, and venue-specific features. The system must survive "
            "adversarial validation (red-team battery) before any live capital "
            "is deployed."
        ),
        "constraints": [
            "No live observer until all promotion gates pass",
            "No lookahead bias in any feature or label",
            "All candidates must pass red-team validation battery",
            "Full-universe collection, eligible-only analysis",
        ],
    }


def section_program_status(root: str) -> dict:
    """Current program status."""
    # Try to read fire log status
    manifest_path = os.path.join(root, "reports/synthesis/feature_tape_v2_final_manifest.json")
    manifest = _read_file_safe(manifest_path)

    # Check if collection is active
    tape_status = "COLLECTING"
    fire_count = "unknown"
    if manifest:
        try:
            m = json.loads(manifest)
            fire_count = m.get("fire_count", "unknown")
            tape_status = "FROZEN" if m.get("frozen") else "COLLECTING"
        except json.JSONDecodeError:
            pass

    return {
        "title": "Current Program Status",
        "feature_tape_v2": {
            "status": tape_status,
            "fire_count": fire_count,
            "collection_scope": "full_universe",
            "analysis_scope": "eligible_only (primary), full_universe (audit)",
        },
        "active_services": [
            "feature_tape_v2.py — collecting every 15m fire",
            "feature_tape_v2_autopilot.sh — waiting for 96 fires + label maturity",
        ],
        "inactive_services": [
            "No live observer running",
            "No live trading",
            "No dashboard",
        ],
        "phase": "Data collection + cold-path infra build",
    }


def section_benchmark_suite(root: str) -> dict:
    """Benchmark suite summary."""
    return {
        "title": "Benchmark Suite v1",
        "description": "Baseline performance from v1 momentum sweep (11 features, 5 horizons)",
        "key_results": {
            "baseline_gross_median_15m": 0.0,
            "baseline_net_median_15m": -0.005,
            "best_v1_gross_median_15m": 0.002,
            "best_v1_net_median_15m": -0.003,
        },
        "conclusion": "No v1 momentum feature survived net costs. All entered no-go registry.",
    }


def section_nogo_registry(root: str) -> dict:
    """No-go registry summary."""
    return {
        "title": "No-Go Registry v1",
        "description": "Features proven to have no edge after costs. Must not be re-tested without structural distinction.",
        "entries": [
            {"family": "momentum_direction", "feature": "r_m5"},
            {"family": "momentum_direction", "feature": "buy_sell_ratio_m5"},
            {"family": "momentum_direction", "feature": "vol_accel_m5_vs_h1"},
            {"family": "momentum_direction", "feature": "txn_accel_m5_vs_h1"},
            {"family": "momentum_direction", "feature": "rv_5m"},
            {"family": "momentum_direction", "feature": "range_5m"},
            {"family": "momentum_direction", "feature": "buy_count_ratio_m5"},
            {"family": "momentum_direction", "feature": "avg_trade_usd_m5"},
            {"family": "momentum_direction", "feature": "liq_change_pct"},
            {"family": "momentum_direction", "feature": "breadth_positive_pct"},
            {"family": "momentum_direction", "feature": "pool_dispersion_r_m5"},
        ],
        "count": 11,
    }


def section_dataset_index(root: str) -> dict:
    """Dataset index summary."""
    idx_path = os.path.join(root, "reports/research/dataset_index.md")
    idx_content = _read_file_safe(idx_path)

    return {
        "title": "Dataset Index",
        "datasets": [
            {"name": "universe_snapshot", "description": "15-min scanner snapshots of eligible + ineligible tokens"},
            {"name": "microstructure_log", "description": "Per-pool order flow metrics (5m + 1h windows)"},
            {"name": "feature_tape_v2", "description": "Joined feature tape with 62 columns, full-universe"},
            {"name": "feature_tape_v2_fire_log", "description": "Per-fire metadata (timing, counts)"},
        ],
        "full_index_available": idx_content is not None,
    }


def section_feature_acquisition_v2(root: str) -> dict:
    """Feature acquisition v2 status."""
    design_path = os.path.join(root, "reports/synthesis/feature_acquisition_v2_design_note.md")
    design_exists = _read_file_safe(design_path) is not None

    return {
        "title": "Feature Acquisition v2 Status",
        "design_note_exists": design_exists,
        "planned_families": [
            {
                "id": 1,
                "name": "Trade-by-trade order flow / urgency",
                "status": "data collection in progress",
                "priority": "highest",
            },
            {
                "id": 2,
                "name": "Cross-venue flow divergence",
                "status": "deferred until family 1 completes",
                "priority": "medium",
            },
            {
                "id": 3,
                "name": "Large-cap swing (event study)",
                "status": "scaffold built, execution deferred",
                "priority": "fallback",
            },
        ],
        "collection_target": "96 fires (24 hours)",
        "holdout_design": "75/25 temporal split, 8 promotion gates, 6 kill gates",
    }


def section_open_questions(root: str) -> dict:
    """Exact open questions."""
    return {
        "title": "Open Questions",
        "questions": [
            {
                "id": "OQ1",
                "question": "Does any v2 feature family survive the red-team battery after costs?",
                "blocking": True,
                "expected_answer_date": "After 96 fires + label maturity (~48h from collection start)",
            },
            {
                "id": "OQ2",
                "question": "Is the eligible-only universe large enough for statistical power?",
                "blocking": False,
                "expected_answer_date": "After 10-fire checkpoint",
            },
            {
                "id": "OQ3",
                "question": "Should lane be renamed to universe_category in v3?",
                "blocking": False,
                "expected_answer_date": "After v2 sweep completes",
            },
        ],
    }


def section_next_decision_gate(root: str) -> dict:
    """Exact next decision gate."""
    return {
        "title": "Next Decision Gate",
        "gate": "Feature Tape v2 Final Recommendation",
        "trigger": "96 fires collected + all label horizons mature (+5m through +4h)",
        "decision_options": [
            "PROCEED — launch live observer for best candidate family",
            "PIVOT — switch to fallback strategy (large-cap swing)",
            "STOP — no viable edge found; pause program",
        ],
        "decision_maker": "Human operator (not automated)",
        "automated_input": "reports/synthesis/feature_family_sweep_v2_final_recommendation.md",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Output formatters
# ══════════════════════════════════════════════════════════════════════════════

def build_packet(root: str) -> dict:
    """Assemble the full packet."""
    return {
        "packet_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "solana-narrative-trader",
        "sections": [
            section_project_goal(root),
            section_program_status(root),
            section_benchmark_suite(root),
            section_nogo_registry(root),
            section_dataset_index(root),
            section_feature_acquisition_v2(root),
            section_open_questions(root),
            section_next_decision_gate(root),
        ],
    }


def write_markdown(packet: dict, output_dir: str):
    """Write packet as Markdown."""
    lines = [
        "# External Review Packet",
        f"**Generated:** {packet['generated_at']}",
        f"**Project:** {packet['project']}",
        "",
        "---",
        "",
    ]

    for section in packet["sections"]:
        title = section.get("title", "Untitled")
        lines.append(f"## {title}")
        lines.append("")

        # Render section content based on structure
        for key, value in section.items():
            if key == "title":
                continue
            if isinstance(value, str):
                lines.append(f"**{key}:** {value}")
            elif isinstance(value, bool):
                lines.append(f"**{key}:** {'Yes' if value else 'No'}")
            elif isinstance(value, (int, float)):
                lines.append(f"**{key}:** {value}")
            elif isinstance(value, list):
                lines.append(f"**{key}:**")
                for item in value:
                    if isinstance(item, dict):
                        parts = [f"{k}: {v}" for k, v in item.items()]
                        lines.append(f"- {' | '.join(parts)}")
                    else:
                        lines.append(f"- {item}")
            elif isinstance(value, dict):
                lines.append(f"**{key}:**")
                for k, v in value.items():
                    lines.append(f"- {k}: {v}")
            lines.append("")

        lines.append("---")
        lines.append("")

    path = Path(output_dir) / "external_review_packet.md"
    path.write_text("\n".join(lines) + "\n")
    log.info("Markdown packet: %s", path)


def write_yaml(packet: dict, output_dir: str):
    """Write packet as YAML (manual serialization to avoid PyYAML dependency)."""
    lines = []

    def _yaml_value(v, indent=0):
        prefix = "  " * indent
        if v is None:
            return "null"
        elif isinstance(v, bool):
            return "true" if v else "false"
        elif isinstance(v, (int, float)):
            return str(v)
        elif isinstance(v, str):
            if "\n" in v or ":" in v or "#" in v or len(v) > 80:
                return f'"{v}"'
            return v
        elif isinstance(v, list):
            result = []
            for item in v:
                if isinstance(item, dict):
                    result.append(f"\n{prefix}  -")
                    for k2, v2 in item.items():
                        result.append(f"{prefix}    {k2}: {_yaml_value(v2, indent + 2)}")
                else:
                    result.append(f"\n{prefix}  - {_yaml_value(item, indent + 1)}")
            return "".join(result)
        elif isinstance(v, dict):
            result = []
            for k2, v2 in v.items():
                val = _yaml_value(v2, indent + 1)
                if isinstance(v2, (list, dict)) and v2:
                    result.append(f"\n{prefix}  {k2}: {val}")
                else:
                    result.append(f"\n{prefix}  {k2}: {val}")
            return "".join(result)
        return str(v)

    lines.append(f"packet_version: \"{packet['packet_version']}\"")
    lines.append(f"generated_at: \"{packet['generated_at']}\"")
    lines.append(f"project: {packet['project']}")
    lines.append("sections:")

    for section in packet["sections"]:
        lines.append(f"  - title: \"{section.get('title', 'Untitled')}\"")
        for key, value in section.items():
            if key == "title":
                continue
            lines.append(f"    {key}: {_yaml_value(value, 2)}")

    path = Path(output_dir) / "external_review_packet.yaml"
    path.write_text("\n".join(lines) + "\n")
    log.info("YAML packet: %s", path)


def write_json(packet: dict, output_dir: str):
    """Write packet as JSON."""
    path = Path(output_dir) / "external_review_packet.json"
    path.write_text(json.dumps(packet, indent=2, default=str) + "\n")
    log.info("JSON packet: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Build External Review Packet")
    parser.add_argument("--output-dir", default="reports/external_review/",
                        help="Output directory")
    parser.add_argument("--format", choices=["markdown", "yaml", "json", "all"],
                        default="all", help="Output format(s)")
    args = parser.parse_args()

    root = _find_project_root()
    log.info("Project root: %s", root)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    packet = build_packet(root)

    if args.format in ("markdown", "all"):
        write_markdown(packet, str(output_dir))
    if args.format in ("yaml", "all"):
        write_yaml(packet, str(output_dir))
    if args.format in ("json", "all"):
        write_json(packet, str(output_dir))

    log.info("External review packet generated in: %s", output_dir)


if __name__ == "__main__":
    main()
