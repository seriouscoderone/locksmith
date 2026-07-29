"""A minimal micro-app template shaped like the real ones (commands[]/projections[]),
plus one command carrying a never-verb route to prove structural exclusion.
"""

SAMPLE_TEMPLATE = {
    "d": "EFixtureTemplateSAID000000000000000000000000",
    "spec_version": "micro-app-template/0.1",
    "header": {"id": "carrier-quote", "display_name": "Carrier — submit quote"},
    "role": {"id": "carrier", "kind": "organization"},
    "commands": [
        {
            "id": "submit_quote",
            "name": "Submit quote",
            "description": "Send the prepared quote to the counterparty",
            "route": "/insurance/cmd/submit_quote",
            "counterparty_role": "broker",
            "payload_schema": {"type": "object", "properties": {"amount": {"type": "number"}},
                               "required": ["amount"], "additionalProperties": False},
            "authz": {"method": "credential", "schema_said": "ESchemaQuote0000000000000000000000000000000"},
        },
        {
            "id": "create_application",
            "name": "Create application",
            "description": "Open a new application record",
            "route": "/insurance/cmd/create_application",
            "counterparty_role": None,
            "payload_schema": {"type": "object", "properties": {}, "additionalProperties": True},
            "authz": {"method": "open"},
        },
        {
            # MUST be dropped by the surface builder (never-verb route).
            "id": "rotate_signing_key",
            "name": "Rotate signing key",
            "description": "rotate the carrier key",
            "route": "/keri/cmd/rotate_key",
            "payload_schema": {"type": "object"},
            "authz": {"method": "open"},
        },
    ],
    "projections": [
        {"id": "issued_credentials", "name": "Issued credentials", "display": {"view_type": "table"}},
    ],
}
