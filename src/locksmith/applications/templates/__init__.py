# -*- encoding: utf-8 -*-
"""
locksmith.applications.templates package

Industry-archetype templates for KERI-native applications. Each template
captures the *roles*, *schemas*, and *application manifests* that recur
across deployments of a given industry vertical.

Templates are exemplars, not factories: an instance copies the template's
manifest values and customizes the deployment-specific bits (organization
name in prose, state, jurisdiction, etc.). Schemas are content-addressed,
so multiple instances using the same template share identical schema
SAIDs — that's how cross-org interop emerges from independent deployments.
"""
