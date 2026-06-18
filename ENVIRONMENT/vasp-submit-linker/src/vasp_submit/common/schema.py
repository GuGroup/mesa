from __future__ import annotations

import copy


SAFE_SEGMENT_PATTERN = r"^(?!\.\.?$)[A-Za-z0-9._-]+$"
SAFE_RELATIVE_PATH_PATTERN = r"^(?!.*(?:^|/)\.{1,2}(?:/|$))[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"


PARTIAL_JOB_SPEC_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "job_name": {"type": "string", "pattern": SAFE_SEGMENT_PATTERN},
        "task": {"type": "string", "enum": ["bulk", "slab", "freq", "static"]},
        "project": {
            "oneOf": [
                {"type": "null"},
                {"type": "string", "pattern": SAFE_SEGMENT_PATTERN},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "pattern": SAFE_SEGMENT_PATTERN},
                        "job_dir": {"type": "string", "pattern": SAFE_RELATIVE_PATH_PATTERN},
                        "overwrite": {"type": "boolean"},
                    },
                },
            ],
        },
        "job_dir": {"type": "string", "pattern": SAFE_RELATIVE_PATH_PATTERN},
        "overwrite": {"type": "boolean"},
        "structure": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "format": {"type": "string", "const": "poscar"},
                "content": {"type": "string"},
                "path": {"type": "string", "pattern": SAFE_RELATIVE_PATH_PATTERN},
            },
            "oneOf": [
                {"required": ["format", "content"], "not": {"required": ["path"]}},
                {"required": ["format", "path"], "not": {"required": ["content"]}},
            ],
        },
        "vasp": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "xc": {"type": "string"},
                "kpts": {
                    "type": "array",
                    "prefixItems": [
                        {"type": "integer"},
                        {"type": "integer"},
                        {"type": "integer"},
                    ],
                    "minItems": 3,
                    "maxItems": 3,
                },
                "gamma": {"type": "boolean"},
                "parameters": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        },
        "queue": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": ["auto", "preset48gam", "preset48std", "preset64gam", "preset64std"],
                },
                "submit": {"type": "boolean"},
            },
        },
    },
}

# The final job spec that `vasp-job` consumes. `vasp-job schema` prints this so
# an agent can discover the accepted input shape without reading the docs.
JOB_SPEC_SCHEMA: dict[str, object] = copy.deepcopy(PARTIAL_JOB_SPEC_SCHEMA)
JOB_SPEC_SCHEMA["$schema"] = "https://json-schema.org/draft/2020-12/schema"
JOB_SPEC_SCHEMA["title"] = "vasp-job job spec"
JOB_SPEC_SCHEMA["required"] = ["job_name", "structure"]
