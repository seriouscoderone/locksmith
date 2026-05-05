# -*- encoding: utf-8 -*-
"""
locksmith.plugins.carrier_appointment package

Carrier Appointment — slice 2. An insurance carrier issues
`CarrierAppointment` credentials authorizing licensed producers to
write specified product lines on the carrier's paper. Each appointment
chains via an edge to the producer's underlying `ProducerLicense`,
making the appointment cryptographically conditional on the license.
"""
