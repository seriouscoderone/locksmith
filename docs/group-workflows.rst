Group Workflows
===============

This slice documents the dialog-level workflows behind the group identifier
section of an open vault.

Covered dialogs:

- ``locksmith.ui.vault.groups.create``
- ``locksmith.ui.vault.groups.view``
- ``locksmith.ui.vault.groups.interact``
- ``locksmith.ui.vault.groups.rotate``
- ``locksmith.ui.vault.groups.authenticate``
- ``locksmith.ui.vault.groups.delete``
- ``locksmith.ui.vault.groups.accept_multisig``
- ``locksmith.ui.vault.groups.accept_rotation``

Create A Group Identifier
-------------------------

``CreateGroupIdentifierDialog`` collects the local signing member, selected
participants, thresholds, optional delegation inputs, and TOAD settings needed
to start a multisig inception.

The dialog validates that the proposed participant set does not duplicate an
existing group habitat before starting the creation flow.

Inspect A Group Identifier
--------------------------

``ViewGroupIdentifierDialog`` is the read-heavy details view for an existing
group habitat. It shows the AID, KEL, KEL metadata, resubmit controls, witness
OOBIs when present, and the group-specific key-state refresh path.

Interact, Rotate, And Authenticate
----------------------------------

``GroupInteractDialog`` is the lightweight interaction-event path for an
existing group identifier.

``RotateGroupIdentifierDialog`` is the main rotation workflow. It collects new
thresholds, member changes, and witness changes before starting the group
rotation process.

``GroupWitnessAuthenticationDialog`` handles the follow-on witness
authentication step, both as part of a fresh rotation and as a retry path when
authentication remains pending.

Delete A Group Identifier
-------------------------

``DeleteGroupIdentifierDialog`` wraps the shared resource-deletion dialog and
binds it to the identifier-removal helper for group habitats.

Accept Incoming Group Proposals
-------------------------------

``AcceptMultisigProposalDialog`` renders an incoming group inception proposal,
including the participant set and thresholds, then lets the local controller
choose the signing member used to join the group.

``AcceptMultisigRotationDialog`` does the same for incoming group rotation
proposals, including current and next sequence numbers plus witness changes.