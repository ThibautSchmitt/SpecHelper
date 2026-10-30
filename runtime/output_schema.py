"""Adapt declarative output schemas to Codex's strict structured-output contract."""

import copy


def strict_output_schema(schema):
    result = copy.deepcopy(schema)

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            # The Responses strict subset rejects annotation siblings of $ref.
            # A single alternative preserves both reference semantics and field help.
            if "$ref" in value and len(value) > 1:
                value["anyOf"] = [{"$ref": value.pop("$ref")}]
            # Pydantic discriminated unions emit oneOf; the supported strict subset
            # uses anyOf. Literal kind tags keep the alternatives disjoint.
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
            value.pop("discriminator", None)
            if "properties" in value:
                value["required"] = list(value["properties"])
                value["additionalProperties"] = False
            for child in value.values():
                visit(child)

    visit(result)
    return result
