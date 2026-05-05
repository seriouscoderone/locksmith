# -*- encoding: utf-8 -*-
"""
locksmith.applications.instances package

Concrete deployments of templates from locksmith.applications.templates.

Each instance binds an industry template to a specific organization (its
AID, its name in prose, its jurisdiction). Instances are *full copies* of
their template's exemplar Application value, not parameterized factories —
the customized prose and structural choices stay readable at the source
level.

Schemas are content-addressed and stay shared with the template (instances
reference the template's schema files via schema_path); SAIDs are
identical across all instances of the same template.
"""
