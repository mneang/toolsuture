from decimal import Decimal, ROUND_HALF_UP


class CompatibilityRuntimeError(Exception):
    pass


def values_match(actual, expected) -> bool:
    if isinstance(expected, (int, float)):
        try:
            return (
                Decimal(str(actual))
                == Decimal(str(expected))
            )
        except Exception:
            return False

    return actual == expected


def enforce_scope(
    old_args: dict,
    plan: dict,
) -> None:
    scope = plan.get("scope")

    if scope == "GENERAL":
        return

    if scope != "INCIDENT_ONLY":
        raise CompatibilityRuntimeError(
            f"Unsupported repair scope: {scope}"
        )

    for constraint in plan.get(
        "scope_constraints", []
    ):
        field = constraint["field"]
        expected = constraint["expected_value"]

        if field not in old_args:
            raise CompatibilityRuntimeError(
                f"Missing scoped argument: {field}"
            )

        if not values_match(
            old_args[field],
            expected,
        ):
            raise CompatibilityRuntimeError(
                "Compatibility patch scope "
                f"mismatch for {field}"
            )


def request_operations(plan: dict) -> list:
    # New bidirectional format.
    if "request_operations" in plan:
        return plan["request_operations"]

    # Backward compatibility with the already-proven
    # safe-return repair plan.
    return plan.get("operations", [])


def compile_request(
    old_args: dict,
    plan: dict,
) -> dict:
    enforce_scope(old_args, plan)

    new_args = {}

    for operation in request_operations(plan):
        kind = operation["operation"]
        source = operation.get("source_field")
        target = operation["target_field"]

        if kind == "COPY":
            if source not in old_args:
                raise CompatibilityRuntimeError(
                    f"COPY source missing: {source}"
                )

            new_args[target] = old_args[source]

        elif kind == "MULTIPLY":
            if source not in old_args:
                raise CompatibilityRuntimeError(
                    f"MULTIPLY source missing: {source}"
                )

            factor = operation.get("factor")

            if factor is None:
                raise CompatibilityRuntimeError(
                    f"MULTIPLY factor missing: {target}"
                )

            raw_value = Decimal(
                str(old_args[source])
            )

            converted = (
                raw_value
                * Decimal(str(factor))
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )

            new_args[target] = int(converted)

        elif kind == "CONSTANT":
            if operation.get("value") is None:
                raise CompatibilityRuntimeError(
                    f"CONSTANT value missing: {target}"
                )

            new_args[target] = operation["value"]

        else:
            raise CompatibilityRuntimeError(
                f"Unsupported request operation: {kind}"
            )

    return new_args


def normalize_response(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(
            mode="json"
        )

    return value


def get_path(
    response: dict,
    path: str,
):
    current = normalize_response(response)

    for part in path.split("."):
        current = normalize_response(current)

        if not isinstance(current, dict):
            raise CompatibilityRuntimeError(
                f"Response path is not an object: {path}"
            )

        if part not in current:
            raise CompatibilityRuntimeError(
                f"Response path missing: {path}"
            )

        current = current[part]

    return normalize_response(current)


def adapt_response(
    new_response,
    plan: dict,
) -> dict:
    new_response = normalize_response(
        new_response
    )

    operations = plan.get(
        "response_operations", []
    )

    # Legacy request-only repairs do not need
    # response reconstruction.
    if not operations:
        return new_response

    old_response = {}

    for operation in operations:
        kind = operation["operation"]
        source = operation.get("source_field")
        target = operation["target_field"]

        if kind == "EXTRACT":
            old_response[target] = get_path(
                new_response,
                source,
            )

        elif kind == "ENUM_MAP":
            source_value = get_path(
                new_response,
                source,
            )

            entries = operation.get(
                "value_map"
            ) or []

            match = next(
                (
                    item["target_value"]
                    for item in entries
                    if item["source_value"]
                    == source_value
                ),
                None,
            )

            if match is None:
                raise CompatibilityRuntimeError(
                    "No authoritative enum mapping "
                    f"for {source}={source_value!r}"
                )

            old_response[target] = match

        elif kind == "CONSTANT":
            if operation.get("value") is None:
                raise CompatibilityRuntimeError(
                    f"Response CONSTANT missing: {target}"
                )

            old_response[target] = (
                operation["value"]
            )

        else:
            raise CompatibilityRuntimeError(
                f"Unsupported response operation: {kind}"
            )

    return old_response
