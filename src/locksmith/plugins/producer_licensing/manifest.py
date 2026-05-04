# -*- encoding: utf-8 -*-
"""
locksmith.plugins.producer_licensing.manifest module

The Application manifest for Producer Licensing — slice 1.

Hand-instantiated for now. A future Skill walks the 10-step modeling
process and emits a structurally identical Python value.
"""
from __future__ import annotations

from locksmith.applications import (
    Application,
    AttributeDef,
    AuthorizationDef,
    CommandDef,
    CommitsTo,
    CredentialDef,
    EventDef,
    GateDef,
    PreconditionsDef,
    ProjectionDef,
    RegistryDef,
)


PRODUCER_LICENSING = Application(
    id="producer-licensing",
    name="Producer Licensing",
    description=(
        "Usurance, operating as an explicit proxy Department of Insurance "
        "authority for California, issues producer licenses with "
        "line-of-authority designations. The proxy ledger certifies licensure "
        "under Usurance's parallel record-keeping until the real California DOI "
        "bootstraps an AID on this substrate. See docs/usurance-proxy-doi.md "
        "for the migration plan."
    ),
    registries=[
        RegistryDef(
            id="producer-license-registry",
            name="Producer License Registry",
        ),
    ],
    credentials=[
        CredentialDef(
            id="ProducerLicense",
            registry_id="producer-license-registry",
            schema_path="schema/producer_license.json",
            attributes={
                "producerAID": AttributeDef(
                    type="aid",
                    description="Issuee AID (the licensed producer)",
                ),
                "licenseNumber": AttributeDef(
                    type="string",
                    description="Unique license number issued by the DOI",
                ),
                "linesOfAuthority": AttributeDef(
                    type="array<string>",
                    description="Lines of authority covered by this license",
                    enum=["P&C", "Life", "Health", "Surplus Lines"],
                    min_items=1,
                ),
                "state": AttributeDef(
                    type="string",
                    description="Two-letter US state code where the license is valid",
                    min_length=2,
                    max_length=2,
                ),
                "issuedDate": AttributeDef(
                    type="iso8601-date",
                    description="Date the license was issued",
                ),
                "expiresDate": AttributeDef(
                    type="iso8601-date",
                    description="Date the license expires",
                ),
            },
            edges={},
            rule=(
                "This credential is issued by Usurance acting as an explicit proxy "
                "Department of Insurance authority for the named state. Until the real "
                "DOI's AID is bootstrapped on this substrate, this credential certifies "
                "licensure under Usurance's proxy ledger and is intended for relying "
                "parties who explicitly accept the proxy. Reissuance under the real "
                "DOI's AID, or delegation handoff to it, is intended once available; "
                "see docs/usurance-proxy-doi.md. "
                "Substantively: the credential certifies that the bearer (producerAID) "
                "is licensed to act as an insurance producer in the named state for the "
                "listed linesOfAuthority, valid from issuedDate through expiresDate, and "
                "is currently in good standing per the issuer's TEL."
            ),
        ),
    ],
    commands=[
        CommandDef(
            id="IssueProducerLicense",
            payload={
                "producerAID": "aid",
                "licenseNumber": "string",
                "linesOfAuthority": "array<string>",
                "state": "string",
                "issuedDate": "iso8601-date",
                "expiresDate": "iso8601-date",
            },
            authorization=AuthorizationDef(
                principal="control_of(issuer_aid)",
                credential_pattern=None,
            ),
            preconditions=PreconditionsDef(
                state=[
                    "no active license with this licenseNumber exists in registry",
                ],
                temporal=[
                    "expiresDate > issuedDate",
                    "issuedDate <= now",
                ],
            ),
            idempotency_key="licenseNumber",
            produces=["ProducerLicenseIssued"],
            issues="ProducerLicense",
            grants_to="producerAID",
        ),
    ],
    events=[
        EventDef(
            id="ProducerLicenseIssued",
            commits_to=CommitsTo(
                prior_event=True,
                command=True,
                credential_presentation=False,
                credential_issued="ProducerLicense",
                registry_id="producer-license-registry",
            ),
            payload_fields=[
                "producerAID",
                "licenseNumber",
                "linesOfAuthority",
                "state",
                "issuedDate",
                "expiresDate",
            ],
        ),
    ],
    projections=[
        ProjectionDef(
            id="LicensesIssuedByMe",
            lens="issuer",
            gate=GateDef(principal="control_of(issuer_aid)"),
            source="fold over producer-license-registry TEL",
            shape=[
                "licenseNumber",
                "producerAID",
                "state",
                "linesOfAuthority",
                "issuedDate",
                "expiresDate",
                "status",
            ],
            freshness="eager",
        ),
        ProjectionDef(
            id="MyLicense",
            lens="holder",
            gate=GateDef(
                credential_pattern="schema=ProducerLicense, holder=my_aid",
            ),
            source="fold over producer-license-registry TEL filtered by my AID",
            shape=[
                "licenseNumber",
                "state",
                "linesOfAuthority",
                "issuedDate",
                "expiresDate",
                "status",
            ],
            freshness="eager",
        ),
        ProjectionDef(
            id="LicenseLookup",
            lens="public",
            gate=GateDef(public=True),
            query_input="producerAID",
            source="registry TEL",
            shape=[
                "licenseNumber",
                "state",
                "linesOfAuthority",
                "issuedDate",
                "expiresDate",
                "status",
            ],
            freshness="eager",
        ),
    ],
    subscriptions=[],
    policies=[],
)
