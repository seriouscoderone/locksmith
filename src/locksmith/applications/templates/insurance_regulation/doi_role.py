# -*- encoding: utf-8 -*-
"""
locksmith.applications.templates.insurance_regulation.doi_role module

Application manifest exemplar for the Department of Insurance role.

This is the *template* form — generic prose, no specific organization
named. Deployments copy this value and customize per-org (state code in
prose, organization name, proxy-vs-real-DOI disclosure language, etc.).
See docs/usurance-proxy-doi.md for the proxy convention currently in use
until real state DOIs bootstrap KERI presence.
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


DOI_ROLE_TEMPLATE = Application(
    id="insurance-regulation.doi-role",
    name="Department of Insurance — Producer Licensing",
    description=(
        "An authority operating in the Department of Insurance role for a "
        "given U.S. state issues producer licenses with line-of-authority "
        "designations. Until a given state's real DOI bootstraps a KERI AID, "
        "deployments operate as explicit proxies and disclose that in the "
        "issued credential's rule prose."
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
            schema_path="schemas/producer_license.json",
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
                "This credential certifies that the bearer (producerAID) is "
                "licensed to act as an insurance producer in the named state "
                "for the listed linesOfAuthority, valid from issuedDate through "
                "expiresDate, and is currently in good standing per the issuing "
                "authority's TEL. Deployments operating as proxies (i.e., until "
                "the real state DOI bootstraps a KERI AID) MUST extend this "
                "rule with explicit proxy disclosure and a citation to the "
                "deployment's migration plan."
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
