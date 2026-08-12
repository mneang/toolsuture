import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ANSWER_KEY = (
    ROOT
    / "evidence"
    / "evaluation"
    / "blind-v1"
    / "answer-key.json"
)

SCENARIOS = (
    ROOT
    / "evidence"
    / "scenarios"
)


def main():
    key = json.loads(
        ANSWER_KEY.read_text()
    )

    rows = []
    total_checks = 0
    passed_checks = 0

    for scenario, expected in key.items():
        scenario_dir = (
            SCENARIOS / scenario
        )

        diagnosis_path = (
            scenario_dir
            / "diagnosis.json"
        )

        policy_path = (
            scenario_dir
            / "policy.json"
        )

        if (
            not diagnosis_path.exists()
            or not policy_path.exists()
        ):
            rows.append({
                "scenario": scenario,
                "status": "NOT_RUN",
            })
            continue

        diagnosis = json.loads(
            diagnosis_path.read_text()
        )

        policy = json.loads(
            policy_path.read_text()
        )

        checks = {
            "decision":
                diagnosis.get("decision")
                == expected["decision"],

            "gate":
                policy.get("gate")
                == expected["gate"],

            "auto_repair_allowed":
                policy.get(
                    "auto_repair_allowed"
                )
                == expected[
                    "auto_repair_allowed"
                ],
        }

        total_checks += len(checks)
        passed_checks += sum(
            checks.values()
        )

        rows.append({
            "scenario": scenario,
            "expected_decision":
                expected["decision"],

            "actual_decision":
                diagnosis.get("decision"),

            "expected_gate":
                expected["gate"],

            "actual_gate":
                policy.get("gate"),

            "checks":
                checks,

            "passed":
                all(checks.values()),
        })

    completed = [
        row
        for row in rows
        if row.get("status")
        != "NOT_RUN"
    ]

    cases_passed = sum(
        bool(row.get("passed"))
        for row in completed
    )

    result = {
        "evaluation":
            "blind-v1",

        "cases_total":
            len(key),

        "cases_completed":
            len(completed),

        "cases_passed":
            cases_passed,

        "case_accuracy":
            (
                cases_passed
                / len(completed)
                if completed
                else 0
            ),

        "check_accuracy":
            (
                passed_checks
                / total_checks
                if total_checks
                else 0
            ),

        "results":
            rows,
    }

    output = (
        ROOT
        / "evidence"
        / "evaluation"
        / "blind-v1"
        / "results.json"
    )

    output.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
