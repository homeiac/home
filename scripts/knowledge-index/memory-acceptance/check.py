"""Score private photo-memory acceptance captures using only the standard library."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import unicodedata


# Each field is a required observation. Sets are unique rows in arbitrary order.
# The oracle supplies expected rows. Safety invariants are fixed by the contract.
COMMON = {
    "identity": {
        "canonical_query_matches": "rows", "alias_query_matches": "rows",
        "multiple_confirmed_people": "rows", "newly_confirmed_query_matches": "rows",
        "unconfirmed_claimed_as_named": "empty",
    },
    "context": {
        "displayed_primary_captions": "names", "reviewed_person_action_rows": "rows",
        "place_date_source_precision_rows": "rows", "input_revision_rows": "rows",
        "unsupported_claims": "empty", "source_captions_changed": "zero",
        "painted_figures_assigned_real_identities": "empty",
    },
    "retrieval": {
        "resolved_query_facts": "rows", "eligible_pool": "rows",
        "uncertain_or_excluded_with_reasons": "rows",
    },
    "selection": {
        "ordered_highlight_assets": "sequence", "represented_year_or_event_groups": "rows",
        "wrong_subject_inclusions": "empty",
    },
    "delivery": {
        "opened_album_assets": "rows", "reachable_original_assets": "rows",
        "consumer_context_revision_rows": "rows", "private_album_visibility": "private",
    },
    "corrections": {
        "renamed_primary_captions": "names", "query_members_after_edit": "rows",
        "album_members_after_edit": "rows", "corrected_location_rows": "rows",
        "stale_or_pending_before_refresh": "rows", "rejected_assets_reintroduced": "empty",
        "convergence_seconds": "deadline",
    },
    "operations": {
        "album_ids_across_identical_runs": "same_id", "duplicate_album_members": "zero",
        "unchanged_vision_or_speech_calls": "zero", "unchanged_context_model_calls": "zero",
        "unaffected_items_finished_after_bad_item": "rows",
        "isolated_bad_item_dispositions": "rows", "bad_item_attempts": "attempt_limit",
        "post_restart_preserved_edits": "rows",
        "deployed_git_revision": "text", "unauthorized_egress": "empty",
    },
    "accounting": {
        "asset_dispositions": "ledger", "coverage_by_year_and_source": "rows",
        "unresolved_required_assets": "empty",
        "unexplained_scope_gaps": "empty",
    },
}
JOURNEYS = {
    "growing-up": {
        "available_years_covered": "rows", "missing_gps_eligible_assets": "rows",
        "uncertain_dates_reported": "rows",
    },
    "offsite-colleagues": {
        "dated_colleague_memberships": "rows", "travel_and_offsite_evidence": "rows",
        "onsite_or_unsubstantiated_inclusions": "empty",
    },
    "child-pet-friends": {
        "confirmed_pet_and_friend_evidence": "rows", "cooccurrence_mode_and_assets": "rows",
        "unrelated_pets_or_unconfirmed_friends_included": "empty",
    },
}
DEPS = {
    "identity": (), "context": ("identity",), "retrieval": ("identity",),
    "selection": ("retrieval",), "delivery": ("selection", "context"),
    "corrections": ("delivery",), "operations": ("delivery",), "accounting": (),
}
ORACLE = {"rows", "sequence", "names", "text", "deadline", "ledger", "attempt_limit"}
META = ("scope_revision", "release", "surface", "policy_revision", "approval_ref")


def fields(journey):
    return {**COMMON, "retrieval": {**COMMON["retrieval"], **JOURNEYS[journey]}}


def template(journey):
    return {
        "version": 1, "journey": journey, "scope": "reference", "mode": "synthetic",
        **dict.fromkeys(META),
        "expected": {
            task: {key: None for key, op in rules.items() if op in ORACLE}
            for task, rules in fields(journey).items()
        },
    }


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    return isinstance(value, list) and bool(value) and all(map(nonblank, value))


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def words(value):
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(ch if ch.isalnum() else " " for ch in normalized).split()


def includes_name(caption, name):
    tokens, name_tokens = words(caption), words(name)
    return bool(name_tokens) and any(
        tokens[i:i + len(name_tokens)] == name_tokens for i in range(len(tokens))
    )


def valid_oracle(op, value):
    if op in ("rows", "sequence"):
        return strings(value) and len(set(value)) == len(value)
    if op == "ledger":
        if not isinstance(value, dict) or not value:
            return False
        for asset, row in value.items():
            if not nonblank(asset) or not isinstance(row, dict):
                return False
            if row.get("state") == "complete":
                continue
            if row.get("state") not in ("excluded", "withheld", "accepted_exception"):
                return False
            if not all(nonblank(row.get(k)) for k in ("reason", "disposition_ref")):
                return False
        return True
    if op == "names":
        return isinstance(value, dict) and bool(value) and all(
            nonblank(key) and strings(names) and all(words(name) for name in names)
            for key, names in value.items()
        )
    if op == "attempt_limit":
        return type(value) is int and value >= 1
    if op == "deadline":
        return number(value) and value > 0
    return nonblank(value)


def matches(op, expected, actual):
    if op == "rows":
        return strings(actual) and sorted(actual) == sorted(expected)
    if op in ("sequence", "text", "ledger"):
        return actual == expected
    if op == "names":
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            nonblank(actual[key]) and all(includes_name(actual[key], name) for name in names)
            for key, names in expected.items()
        )
    if op == "attempt_limit":
        return type(actual) is int and 1 <= actual <= expected
    if op == "deadline":
        return number(actual) and 0 <= actual <= expected
    if op == "empty":
        return actual == []
    if op == "zero":
        return type(actual) is int and actual == 0
    if op == "same_id":
        return strings(actual) and len(actual) >= 2 and len(set(actual)) == 1
    if op == "private":
        return actual == "private"
    raise ValueError("unknown operator")


def load_object(path):
    data = json.loads(path.read_bytes(), object_pairs_hook=unique_keys)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def valid_artifacts(directory, refs):
    if not isinstance(refs, dict) or not refs:
        return False
    for relative, digest in refs.items():
        if not nonblank(relative) or Path(relative).is_absolute():
            return False
        path = (directory / relative).resolve()
        if directory.resolve() not in path.parents or not path.is_file():
            return False
        data = path.read_bytes()
        if not data or hashlib.sha256(data).hexdigest() != digest:
            return False
    return True


def score_task(directory, task, rules, oracle, binding):
    gaps, failures = [], []
    try:
        capture = load_object(directory / (task + ".json"))
        if any(capture.get(k) != v for k, v in binding.items()):
            return ["wrong run or baseline"], []
        if not valid_artifacts(directory, capture.get("artifacts")):
            return ["missing or altered source evidence"], []
        actual = capture["observed"]
        if not isinstance(actual, dict) or not isinstance(oracle, dict):
            raise ValueError("invalid evidence")
    except (OSError, KeyError, ValueError):
        return ["missing or invalid capture"], []
    for field, op in rules.items():
        expected = oracle.get(field)
        if op in ORACLE and not valid_oracle(op, expected):
            gaps.append("missing oracle " + field)
        elif field not in actual:
            gaps.append("unobserved " + field)
        elif not matches(op, expected, actual[field]):
            failures.append(field)
    return gaps, failures


def evaluate(baseline, directory, run_id):
    plan = load_object(baseline)
    journey = plan.get("journey")
    if (type(plan.get("version")) is not int or plan["version"] != 1
            or journey not in JOURNEYS or plan.get("scope") not in ("reference", "rollout")
            or plan.get("mode") not in ("synthetic", "live") or not nonblank(run_id)
            or not all(nonblank(plan.get(k)) for k in META)
            or not isinstance(plan.get("expected"), dict)):
        raise ValueError("incomplete baseline metadata")
    # The three album checks describe the same selection on distinct surfaces.
    # An inconsistent answer key cannot certify album delivery.
    expected = plan["expected"]
    selection, delivery = expected.get("selection"), expected.get("delivery")
    if isinstance(selection, dict) and isinstance(delivery, dict):
        highlights = selection.get("ordered_highlight_assets")
        if valid_oracle("sequence", highlights):
            for field in ("opened_album_assets", "reachable_original_assets"):
                assets = delivery.get(field)
                if valid_oracle("rows", assets) and set(highlights) != set(assets):
                    raise ValueError("conflicting expected album membership")
            retrieval = expected.get("retrieval")
            pool = retrieval.get("eligible_pool") if isinstance(retrieval, dict) else None
            if valid_oracle("rows", pool) and not set(highlights).issubset(pool):
                raise ValueError("expected highlights outside the eligible pool")
            accounting = expected.get("accounting")
            ledger = accounting.get("asset_dispositions") if isinstance(accounting, dict) else None
            if valid_oracle("ledger", ledger):
                if any(ledger.get(asset, {}).get("state") != "complete" for asset in highlights):
                    raise ValueError("selected asset missing or unresolved in the expected ledger")
                if valid_oracle("rows", pool) and not set(pool).issubset(ledger):
                    raise ValueError("eligible pool extends beyond the declared inventory")
    binding = {"run_id": run_id, "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest()}
    results = {}
    for task, rules in fields(journey).items():
        gaps, failures = score_task(directory, task, rules, plan["expected"].get(task), binding)
        dependencies = [dep for dep in DEPS[task] if results[dep]["status"] != "PASS"]
        status = "FAIL" if failures else "BLOCKED" if gaps or dependencies else "PASS"
        results[task] = {"status": status, "failed": failures, "missing": gaps, "depends_on": dependencies}
    statuses = {r["status"] for r in results.values()}
    overall = "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses else "PASS"
    return {**binding, "journey": journey, "scope": plan["scope"], "mode": plan["mode"],
            "release": plan["release"], "status": overall, "tasks": results}


def platform(directory, run_id):
    reports = {}
    releases = set()
    for journey in JOURNEYS:
        root = directory / journey
        try:
            report = evaluate(root / "baseline.json", root, run_id)
        except (OSError, TypeError, ValueError):
            reports[journey] = "BLOCKED"
            continue
        eligible = (report["journey"], report["scope"], report["mode"]) == (journey, "rollout", "live")
        reports[journey] = report["status"] if eligible else "BLOCKED"
        releases.add(report["release"])
    if "FAIL" in reports.values():
        status = "FAIL"
    elif len(releases) == 1 and all(value == "PASS" for value in reports.values()):
        status = "PASS"
    else:
        status = "BLOCKED"
    return {"status": status, "journeys": reports, "same_release": len(releases) == 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("template", help="print a private baseline scaffold")
    new.add_argument("journey", choices=JOURNEYS)
    check = sub.add_parser("check", help="evaluate a private captured run")
    check.add_argument("baseline", type=Path)
    check.add_argument("capture_directory", type=Path)
    check.add_argument("run_id")
    rollup = sub.add_parser("platform", help="recheck all three live rollout bundles")
    rollup.add_argument("directory", type=Path)
    rollup.add_argument("run_id")
    args = parser.parse_args()
    if args.command == "template":
        print(json.dumps(template(args.journey), indent=2))
        return 0
    try:
        if args.command == "platform":
            report = platform(args.directory, args.run_id)
        else:
            report = evaluate(args.baseline, args.capture_directory, args.run_id)
    except (OSError, TypeError, ValueError):
        print("BLOCKED: invalid or unreadable acceptance baseline", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
