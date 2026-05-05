# -*- encoding: utf-8 -*-
"""
locksmith.applications.templates.insurance_regulation.carrier_role module

Application manifest exemplar for the Insurance Carrier role.

This is the *template* form — generic prose, no specific carrier named.
Deployments copy this value and customize per-org (carrier name in prose,
state/jurisdictions, product lines actually offered, etc.).

Cross-template dependency: the issued CarrierAppointment chains via an
ACDC edge to the producer's ProducerLicense, locked to that schema's SAID
(see PRODUCER_LICENSE_SCHEMA_SAID in the package __init__).
"""
from __future__ import annotations

from locksmith.applications import (
    Application,
    AttributeDef,
    AuthorizationDef,
    CommandDef,
    CommitsTo,
    CredentialDef,
    EdgeDef,
    EventDef,
    GateDef,
    PolicyDef,
    PreconditionsDef,
    ProjectionDef,
    RegistryDef,
    SubscriptionDef,
)
from locksmith.applications.templates.insurance_regulation import (
    PRODUCER_LICENSE_SCHEMA_SAID,
)


CARRIER_ROLE_TEMPLATE = Application(
    id="insurance-regulation.carrier-role",
    name="Insurance Carrier — Producer Appointment",
    description=(
        "An insurance carrier appoints licensed producers to write specific "
        "product lines on the carrier's paper. Each appointment chains via "
        "an ACDC edge to the producer's underlying ProducerLicense, making "
        "the appointment cryptographically conditional on the license."
    ),
    registries=[
        RegistryDef(
            id="carrier-appointment-registry",
            name="Carrier Appointment Registry",
        ),
    ],
    credentials=[
        CredentialDef(
            id="CarrierAppointment",
            registry_id="carrier-appointment-registry",
            schema_path="schemas/carrier_appointment.json",
            attributes={
                "carrierName": AttributeDef(
                    type="string",
                    description="Human-readable carrier name (e.g., 'Acme Insurance Co.')",
                ),
                "productLines": AttributeDef(
                    type="array<string>",
                    description="Product lines this appointment covers",
                    enum=["GL", "PL", "Auto", "Property", "Workers Comp", "Umbrella"],
                    min_items=1,
                ),
                "appointmentNumber": AttributeDef(
                    type="string",
                    description="Carrier's internal appointment identifier",
                ),
                "state": AttributeDef(
                    type="string",
                    description="Two-letter US state code; must match producer's license state",
                    min_length=2,
                    max_length=2,
                ),
                "effectiveDate": AttributeDef(
                    type="iso8601-date",
                    description="Date the appointment becomes effective",
                ),
                "expiresDate": AttributeDef(
                    type="iso8601-date",
                    description="Date the appointment expires",
                ),
            },
            edges={
                "producerLicense": EdgeDef(
                    target_credential_id="ProducerLicense",
                    cardinality="one",
                    # operator left as None — defaults to ACDC's I2I unary operator
                    # for targeted ACDCs (spec-body.md:1099-1108). Revocation-aware
                    # invalidation is handled by SubscriptionDef + PolicyDef below
                    # (spec-body.md:1112 — EGF-dependent, not an edge concern).
                ),
            },
            rule=(
                "This credential certifies that the bearer (the appointed "
                "producer) is authorized by the issuing carrier to write the "
                "listed productLines on the carrier's paper, in the named "
                "state, valid from effectiveDate through expiresDate. The "
                "credential cryptographically commits to the specific "
                "ProducerLicense it depends on via the producerLicense edge. "
                "Revocation of the underlying license does not invalidate "
                "this credential automatically (ACDC has no built-in operator "
                "for that — revocation handling is ecosystem-governance-"
                "framework dependent per spec-body.md:1112). Instead, the "
                "issuing carrier subscribes to ProducerLicense lifecycle "
                "events and reacts to revocations via its own "
                "SuspendDependentAppointments policy."
            ),
        ),
    ],
    commands=[
        CommandDef(
            id="AppointProducer",
            payload={
                "producerAID": "aid",
                "producerLicenseSAID": "string",
                "carrierName": "string",
                "productLines": "array<string>",
                "appointmentNumber": "string",
                "state": "string",
                "effectiveDate": "iso8601-date",
                "expiresDate": "iso8601-date",
            },
            authorization=AuthorizationDef(
                principal="control_of(issuer_aid)",
                credential_pattern=None,
            ),
            preconditions=PreconditionsDef(
                state=[
                    "ProducerLicense referenced by producerLicenseSAID exists in a known TEL",
                    "ProducerLicense.linesOfAuthority covers the appointment's productLines",
                    "ProducerLicense.state matches appointment.state",
                    "no active appointment with this appointmentNumber exists in registry",
                ],
                temporal=[
                    "effectiveDate <= expiresDate",
                    "expiresDate <= ProducerLicense.expiresDate",
                ],
            ),
            idempotency_key="appointmentNumber",
            produces=["ProducerAppointed"],
            issues="CarrierAppointment",
            grants_to="producerAID",
        ),
    ],
    events=[
        EventDef(
            id="ProducerAppointed",
            commits_to=CommitsTo(
                prior_event=True,
                command=True,
                credential_presentation=False,
                credential_issued="CarrierAppointment",
                registry_id="carrier-appointment-registry",
            ),
            payload_fields=[
                "producerAID",
                "appointmentNumber",
                "carrierName",
                "productLines",
                "state",
                "effectiveDate",
                "expiresDate",
            ],
        ),
    ],
    projections=[
        ProjectionDef(
            id="AppointmentsIGranted",
            lens="issuer",
            gate=GateDef(principal="control_of(issuer_aid)"),
            source="fold over carrier-appointment-registry TEL",
            shape=[
                "appointmentNumber",
                "producerAID",
                "carrierName",
                "productLines",
                "state",
                "effectiveDate",
                "expiresDate",
                "status",
            ],
            freshness="eager",
        ),
        ProjectionDef(
            id="MyAppointments",
            lens="holder",
            gate=GateDef(
                credential_pattern="schema=CarrierAppointment, holder=my_aid",
            ),
            source="fold over carrier-appointment-registry TEL filtered by my AID",
            shape=[
                "appointmentNumber",
                "carrierName",
                "productLines",
                "state",
                "effectiveDate",
                "expiresDate",
                "status",
            ],
            freshness="eager",
        ),
        ProjectionDef(
            id="AppointmentLookup",
            lens="public",
            gate=GateDef(public=True),
            query_input="producerAID",
            source="registry TEL",
            shape=[
                "appointmentNumber",
                "carrierName",
                "productLines",
                "state",
                "effectiveDate",
                "expiresDate",
                "status",
            ],
            freshness="eager",
        ),
    ],
    subscriptions=[
        SubscriptionDef(
            id="ProducerLicenseLifecycleFeed",
            schemas=[PRODUCER_LICENSE_SCHEMA_SAID],
            filter=None,
            reaction="SuspendDependentAppointments",
        ),
    ],
    policies=[
        PolicyDef(
            id="SuspendDependentAppointments",
            trigger_event_id="ProducerLicenseRevoked",
            reaction_command_id="SuspendAppointment",
            timeout=None,
            compensation_command_id=None,
        ),
    ],
)
