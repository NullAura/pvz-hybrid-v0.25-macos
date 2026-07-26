#!/usr/bin/env python3
"""Audit every packaged level without changing upstream gameplay data."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from level_gameplay_fixes import apply_gameplay_fixes, load_gameplay_fixes


def load_tree(root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    documents: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for path in sorted(root.rglob("*.json")):
        relative = path.relative_to(root).as_posix()
        try:
            documents[relative] = json.loads(
                path.read_text(encoding="utf-8-sig")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append({"path": relative, "message": str(exc)})
    return documents, errors


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compare_gameplay(
    baseline: Any,
    localized: Any,
    location: str,
    differences: list[dict[str, Any]],
    changed_strings: list[dict[str, str]],
) -> None:
    if type(baseline) is not type(localized):
        if is_number(baseline) and is_number(localized):
            if float(baseline) != float(localized):
                differences.append(
                    {
                        "path": location,
                        "baseline": baseline,
                        "localized": localized,
                    }
                )
            return
        differences.append(
            {
                "path": location,
                "baseline_type": type(baseline).__name__,
                "localized_type": type(localized).__name__,
            }
        )
        return

    if isinstance(baseline, dict):
        baseline_keys = set(baseline)
        localized_keys = set(localized)
        if baseline_keys != localized_keys:
            differences.append(
                {
                    "path": location,
                    "missing_keys": sorted(baseline_keys - localized_keys),
                    "added_keys": sorted(localized_keys - baseline_keys),
                }
            )
        for key in sorted(baseline_keys & localized_keys):
            compare_gameplay(
                baseline[key],
                localized[key],
                f"{location}.{key}",
                differences,
                changed_strings,
            )
        return

    if isinstance(baseline, list):
        if len(baseline) != len(localized):
            differences.append(
                {
                    "path": location,
                    "baseline_length": len(baseline),
                    "localized_length": len(localized),
                }
            )
        for index, (left, right) in enumerate(zip(baseline, localized)):
            compare_gameplay(
                left,
                right,
                f"{location}[{index}]",
                differences,
                changed_strings,
            )
        return

    if isinstance(baseline, str):
        if baseline != localized:
            changed_strings.append(
                {
                    "path": location,
                    "baseline": baseline,
                    "localized": localized,
                }
            )
        return

    if baseline != localized:
        differences.append(
            {
                "path": location,
                "baseline": baseline,
                "localized": localized,
            }
        )


def require_finite_number(
    value: Any,
    location: str,
    issues: list[dict[str, str]],
    *,
    minimum: float | None = None,
    strictly_positive: bool = False,
) -> None:
    if not is_number(value) or not math.isfinite(float(value)):
        issues.append({"path": location, "message": "must be a finite number"})
        return
    if minimum is not None and float(value) < minimum:
        issues.append(
            {"path": location, "message": f"must be at least {minimum:g}"}
        )
    if strictly_positive and float(value) <= 0:
        issues.append({"path": location, "message": "must be greater than zero"})


def audit_wave_manager(
    relative: str,
    document: dict[str, Any],
    issues: list[dict[str, str]],
    statistics: Counter[str],
) -> None:
    manager = document.get("WaveManager")
    if not isinstance(manager, dict):
        return
    statistics["wave_levels"] += 1

    for key in ("BeginCol", "SpawnColStart", "SpawnColEnd"):
        if key in manager:
            require_finite_number(
                manager[key],
                f"{relative}.WaveManager.{key}",
                issues,
                minimum=0,
            )
    if "FlagWaveInterval" in manager:
        require_finite_number(
            manager["FlagWaveInterval"],
            f"{relative}.WaveManager.FlagWaveInterval",
            issues,
            strictly_positive=True,
        )

    start = manager.get("SpawnColStart")
    end = manager.get("SpawnColEnd")
    if is_number(start) and is_number(end) and float(start) > float(end):
        issues.append(
            {
                "path": f"{relative}.WaveManager",
                "message": "SpawnColStart exceeds SpawnColEnd",
            }
        )

    waves = manager.get("Wave")
    if not isinstance(waves, list):
        issues.append(
            {
                "path": f"{relative}.WaveManager.Wave",
                "message": "must be an array",
            }
        )
        return
    statistics["waves"] += len(waves)
    pre_spawn = document.get("PreSpawn")
    has_pre_spawn_content = (
        isinstance(pre_spawn, dict)
        and any(isinstance(value, list) and value for value in pre_spawn.values())
    )
    if not waves and not has_pre_spawn_content:
        issues.append(
            {
                "path": f"{relative}.WaveManager.Wave",
                "message": "wave-based level has no waves",
            }
        )

    for wave_index, wave in enumerate(waves):
        wave_location = f"{relative}.WaveManager.Wave[{wave_index}]"
        if not isinstance(wave, dict):
            issues.append({"path": wave_location, "message": "must be an object"})
            continue
        spawns = wave.get("Spawn", [])
        if not isinstance(spawns, list):
            issues.append(
                {"path": f"{wave_location}.Spawn", "message": "must be an array"}
            )
            continue
        statistics["spawn_groups"] += len(spawns)
        for spawn_index, spawn in enumerate(spawns):
            spawn_location = f"{wave_location}.Spawn[{spawn_index}]"
            if not isinstance(spawn, dict):
                issues.append(
                    {"path": spawn_location, "message": "must be an object"}
                )
                continue
            zombie = spawn.get("Zombie")
            if not isinstance(zombie, str) or not zombie:
                issues.append(
                    {
                        "path": f"{spawn_location}.Zombie",
                        "message": "must name a zombie",
                    }
                )
            number = spawn.get("Num")
            require_finite_number(
                number,
                f"{spawn_location}.Num",
                issues,
                strictly_positive=True,
            )
            if is_number(number) and not float(number).is_integer():
                issues.append(
                    {
                        "path": f"{spawn_location}.Num",
                        "message": "must be an integer",
                    }
                )
            line = spawn.get("Line")
            require_finite_number(
                line,
                f"{spawn_location}.Line",
                issues,
                # -1 is the game's intentional "choose an active lane" value.
                minimum=-1,
            )
            if is_number(line) and not float(line).is_integer():
                issues.append(
                    {
                        "path": f"{spawn_location}.Line",
                        "message": "must be an integer",
                    }
                )

    dynamics = manager.get("Dynamic", [])
    if not isinstance(dynamics, list):
        issues.append(
            {
                "path": f"{relative}.WaveManager.Dynamic",
                "message": "must be an array",
            }
        )
        return
    for dynamic_index, dynamic in enumerate(dynamics):
        dynamic_location = (
            f"{relative}.WaveManager.Dynamic[{dynamic_index}]"
        )
        if not isinstance(dynamic, dict):
            issues.append(
                {"path": dynamic_location, "message": "must be an object"}
            )
            continue
        for key in (
            "StartingWave",
            "StartingPoints",
            "PointIncrementPerWave",
        ):
            if key in dynamic:
                require_finite_number(
                    dynamic[key],
                    f"{dynamic_location}.{key}",
                    issues,
                    minimum=0 if key == "StartingWave" else None,
                )
        pool = dynamic.get("ZombiePool")
        if pool is not None and (
            not isinstance(pool, list)
            or any(not isinstance(item, str) or not item for item in pool)
        ):
            issues.append(
                {
                    "path": f"{dynamic_location}.ZombiePool",
                    "message": "must contain only zombie names",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--localized-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--gameplay-fixes", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    localized, localized_parse_errors = load_tree(args.localized_root)
    baseline, baseline_parse_errors = load_tree(args.baseline_root)
    gameplay_fixes = load_gameplay_fixes(args.gameplay_fixes)
    missing = sorted(set(baseline) - set(localized))
    added = sorted(set(localized) - set(baseline))
    gameplay_differences: list[dict[str, Any]] = []
    changed_strings: list[dict[str, str]] = []
    for relative in sorted(set(baseline) & set(localized)):
        resource_path = f"Asset/Config/Level/{relative}"
        fixed_text, _ = apply_gameplay_fixes(
            json.dumps(baseline[relative], ensure_ascii=False),
            resource_path,
            gameplay_fixes,
        )
        expected = json.loads(fixed_text)
        compare_gameplay(
            expected,
            localized[relative],
            relative,
            gameplay_differences,
            changed_strings,
        )

    issues: list[dict[str, str]] = []
    statistics: Counter[str] = Counter(
        files=len(localized),
        baseline_files=len(baseline),
        changed_strings=len(changed_strings),
    )
    level_names: Counter[str] = Counter()
    for relative, document in localized.items():
        if not isinstance(document, dict):
            continue
        name = document.get("Name")
        if isinstance(name, str) and name:
            level_names[name] += 1
            statistics["named_levels"] += 1
        audit_wave_manager(relative, document, issues, statistics)
    duplicate_names = sorted(
        name for name, count in level_names.items() if count > 1
    )

    report = {
        "ok": not (
            localized_parse_errors
            or baseline_parse_errors
            or missing
            or added
            or gameplay_differences
            or issues
        ),
        "statistics": dict(sorted(statistics.items())),
        "localized_parse_errors": localized_parse_errors,
        "baseline_parse_errors": baseline_parse_errors,
        "missing_files": missing,
        "added_files": added,
        "gameplay_differences": gameplay_differences,
        "config_issues": issues,
        "duplicate_level_names": duplicate_names,
        "changed_string_samples": changed_strings[:25],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    summary = {
        "ok": report["ok"],
        "statistics": report["statistics"],
        "localized_parse_errors": len(localized_parse_errors),
        "baseline_parse_errors": len(baseline_parse_errors),
        "missing_files": len(missing),
        "added_files": len(added),
        "gameplay_differences": len(gameplay_differences),
        "config_issues": len(issues),
        "config_issue_samples": issues[:10],
        "report": str(args.report) if args.report else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
