# -*- encoding: utf-8 -*-
"""
locksmith.plugins.carrier_appointment.manifest module

The Application manifest for Carrier Appointment — slice 2.

Stresses the format on three axes slice 1 didn't touch:
- EdgeDef with operator (MUST_NOT_REVOKED) chaining to ProducerLicense
- SubscriptionDef referencing another udApp's event schema SAID
- A different issuer role (carrier, not proxy DOI)
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


# Cross-application reference: the ProducerLicense schema SAID published by
# the producer-licensing application. Locked in our schema's edge declaration
# via `s.const` — bytes-level dependency. If producer-licensing's schema ever
# rotates, this SAID + the schema's `const` both need updating.
PRODUCER_LICENSE_SCHEMA_SAID = "ECmEfS_FcGeVLduy-ym1qDx3usSL9J0wwfOlY8kTBg80"


CARRIER_APPOINTMENT = Application(
    id="carrier-appointment",
    name="Carrier Appointment",
    description=(
        "An insurance carrier appoints licensed producers to write specific "
        "product lines on the carrier's paper. Each appointment chains via an "
        "edge to the producer's underlying ProducerLicense, making the "
        "appointment cryptographically conditional on the license remaining "
        "in good standing per the issuing authority's TEL."
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
            schema_path="schema/carrier_appointment.json",
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
                    # for targeted ACDCs (spec-body.md:1099-1108). I2I requires the
                    # chained credential's issuee to equal this credential's issuer
                    # context. Revocation-aware invalidation is NOT an edge-operator
                    # concern in ACDC (spec-body.md:1112 — EGF-dependent); see the
                    # SubscriptionDef + PolicyDef pair below for the mechanism.
                ),
            },
            rule=(
                "This credential certifies that the bearer (the appointed producer) "
                "is authorized by the issuing carrier to write the listed productLines "
                "on the carrier's paper, in the named state, valid from effectiveDate "
                "through expiresDate. The credential cryptographically commits to the "
                "specific ProducerLicense it depends on via the producerLicense edge, "
                "so verifiers can walk the chain and confirm the licensure context. "
                "Revocation of the underlying license does not invalidate this "
                "credential automatically (ACDC has no built-in operator for that — "
                "revocation handling is ecosystem-governance-framework dependent per "
                "spec-body.md:1112). Instead, the issuing carrier subscribes to "
                "ProducerLicense lifecycle events and reacts to revocations via its "
                "own SuspendDependentAppointments policy — see this manifest's "
                "subscriptions and policies."
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
                # Carrier's control of their own AID is the authority. The producer's
                # license is *committed to* via the issued credential's edge, not
                # *presented by* the carrier — this is the bytes-level commitment
                # pattern, not the inbound-presentation pattern.
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
            # When ProducerLicense events surface in any subscribed-to TEL,
            # the carrier reacts. Specifically: revocation of an underlying
            # license should suspend any appointment whose edge chains to it.
            # KERI-native: the subscription is keyed by schema SAID, not by
            # source AID — any DOI (proxy or real) emitting this schema feeds
            # the subscription.
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
