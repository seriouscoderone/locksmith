# -*- encoding: utf-8 -*-
"""
locksmith.applications.instances.acme_insurance_ca.manifest module

Acme Insurance Co.'s California deployment of the
templates.insurance_regulation.carrier_role exemplar.

Acme is a real (fictional) carrier — not a proxy — so the alias and
rule prose are direct. Customizations from the template:
  - description and rule prose mention Acme and California explicitly
  - schema_path points back to the template's canonical schema location

Issuer AID alias used by this deployment: `acme-insurance-ca`.
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


# Issuer AID alias used by this deployment.
ISSUER_ALIAS = "acme-insurance-ca"


ACME_INSURANCE_CA = Application(
    id="acme-insurance-ca",
    name="Acme Insurance Co. — California Producer Appointment",
    description=(
        "Acme Insurance Co. appoints licensed producers to write specific "
        "product lines on Acme's paper in California. Each appointment chains "
        "via an ACDC edge to the producer's underlying ProducerLicense "
        "(typically issued by usurance-proxy-doi-ca during the proxy era), "
        "making the appointment cryptographically conditional on the license."
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
            # Schema lives in the template (content-addressed; shared across
            # all instances of insurance-regulation.carrier-role).
            schema_path="../../templates/insurance_regulation/schemas/carrier_appointment.json",
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
                    # for targeted ACDCs (spec-body.md:1099-1108).
                ),
            },
            rule=(
                "This credential certifies that the bearer (the appointed "
                "producer) is authorized by Acme Insurance Co. to write the "
                "listed productLines on Acme's paper in California, valid "
                "from effectiveDate through expiresDate. The credential "
                "cryptographically commits to the specific ProducerLicense it "
                "depends on via the producerLicense edge. Revocation of the "
                "underlying license does not invalidate this credential "
                "automatically (ACDC has no built-in operator for that — "
                "revocation handling is ecosystem-governance-framework "
                "dependent per spec-body.md:1112). Instead, Acme subscribes "
                "to ProducerLicense lifecycle events and reacts to "
                "revocations via its own SuspendDependentAppointments policy."
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
