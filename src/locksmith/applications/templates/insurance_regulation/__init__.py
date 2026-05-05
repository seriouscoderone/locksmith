# -*- encoding: utf-8 -*-
"""
locksmith.applications.templates.insurance_regulation package

Insurance-regulation industry template. Models the basic chain of
authority in U.S. insurance:

    Department of Insurance (state regulator)
      └─ issues ProducerLicense  ──────────────────────┐
                                                       ▼
    Insurance Carrier (e.g., Acme Insurance)
      └─ issues CarrierAppointment  ─── chains via edge ─── ProducerLicense

The template defines two roles (DOI, Carrier) and the two ACDC schemas
they issue. A specific deployment instantiates one or more roles —
e.g., usurance_proxy_doi_ca is an instance of the DOI role, and
acme_insurance_ca is an instance of the Carrier role.

Schema SAIDs:
- ProducerLicense:       ECmEfS_FcGeVLduy-ym1qDx3usSL9J0wwfOlY8kTBg80
- CarrierAppointment:    ELSeXqzFfDo0gn5Lhat_aj5c8Ohe49oU_DgNT3GnlM3r
"""
PRODUCER_LICENSE_SCHEMA_SAID = "ECmEfS_FcGeVLduy-ym1qDx3usSL9J0wwfOlY8kTBg80"
CARRIER_APPOINTMENT_SCHEMA_SAID = "ELSeXqzFfDo0gn5Lhat_aj5c8Ohe49oU_DgNT3GnlM3r"
