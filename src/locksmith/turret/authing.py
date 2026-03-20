# -*- encoding: utf-8 -*-
"""
Authing for the turret. Slight differences from heki authing
"""

from hio.help import Hict
from keri.end import ending
from keri.help import helping


class Authenticator:
    def __init__(self, hby, method, path, signator=None, root=None, defaultFields=None):
        self.hby = hby
        self.method = method
        self.path = path
        self.root = root
        self.signator = signator
        self.defaultFields = defaultFields

    def sign(self):
        hab = self.hby.habByName(self.signator)
        headers = Hict([
            ("Signify-Resource", hab.pre),
            ("Signify-Timestamp", helping.nowIso8601()),
        ])

        header, qsig = ending.siginput(name="signify", method=self.method, path=self.path, headers=headers,
                                       fields=self.defaultFields, hab=hab, alg="ed25519", keyid=hab.pre)
        headers.extend(header)
        signage = ending.Signage(markers=dict(signify=qsig), indexed=False, signer=None, ordinal=None,
                                 digest=None,
                                 kind=None)
        headers.extend(ending.signature([signage]))

        return dict(headers)

    def verify(self, headers):
        if "signature-input" not in headers or "signature" not in headers:
            return False

        siginput = headers["signature-input"]
        if not siginput:
            return False

        signature = headers["signature"]
        if not signature:
            return False

        inputs = ending.desiginput(siginput.encode("utf-8"))
        inputs = [i for i in inputs if i.name == "signify"]

        if not inputs:
            return False

        for inputage in inputs:
            items = []
            for field in inputage.fields:
                key = field.lower()
                field = field.lower()
                if key not in headers:
                    continue

                value = ending.normalize(headers[key])
                items.append(f'"{field}": {value}')

            values = [f"({' '.join(inputage.fields)})", f"created={inputage.created}"]
            if inputage.expires is not None:
                values.append(f"expires={inputage.expires}")
            if inputage.nonce is not None:
                values.append(f"nonce={inputage.nonce}")
            if inputage.keyid is not None:
                values.append(f"keyid={inputage.keyid}")
            if inputage.context is not None:
                values.append(f"context={inputage.context}")
            if inputage.alg is not None:
                values.append(f"alg={inputage.alg}")

            params = ';'.join(values)

            items.append(f'"@signature-params: {params}"')
            ser = "\n".join(items).encode("utf-8")

            # each individual api/instance
            resource = headers["signify-resource"]

            # is it in kevers? make sure its oobiid
            if resource not in self.hby.kevers:
                return False

            ckever = self.hby.kevers[resource]

            # is the signer a delegated AID from the configured root AID
            # TODO(KERI Foundation): Configure root AID for delegation verification
            if not self.root:
                return False

            if ckever.delpre != self.root:
                return False

            signages = ending.designature(signature)
            cig = signages[0].markers[inputage.name]

            if not ckever.verfers[0].verify(sig=cig.raw, ser=ser):
                return False

        return True
