"""In-process serialized governance writer over the existing catalogue.

No JSON import is treated as trusted issuance. Receipts are instance-local
integrity references, not production signatures or durable authorization.
"""

from threading import RLock
from uuid import uuid4

from ..contracts import reference, reference_key
from .common import GovernanceError, clone, digest


class GovernanceJournal:
    def __init__(self, catalogue):
        self.catalogue = catalogue
        self.lock = RLock()
        self.instance_id = "memory-governance:" + str(uuid4())
        self.head = 0
        self._entries, self._trusted, self._commands = [], {}, {}

    def replay(self, command_id, command_digest):
        cached = self._commands.get(command_id)
        if cached:
            if cached["digest"] != command_digest:
                raise GovernanceError("command_conflict", "Command ID was already used for different input or principal.")
            return clone(cached["outcome"])
        return None

    def check_head(self, expected_head):
        if type(expected_head) is not int or expected_head != self.head:
            raise GovernanceError("stale_governance_head", "Governance state changed; refresh before submitting this action.")

    def commit(self, documents, *, expected_head, command_id, command_digest, outcome):
        self.check_head(expected_head)
        self.catalogue.add_many(documents)  # Existing atomic validation/insert.
        self.head += 1
        previous = self._entries[-1]["entry_digest"] if self._entries else None
        entry = {"sequence": self.head, "command_id": command_id, "references": [reference(d) for d in documents],
                 "document_digests": [digest(d) for d in documents], "previous_entry_digest": previous}
        entry["entry_digest"] = digest(entry)
        for document in documents:
            self._trusted[reference_key(document)] = digest(document)
        self._entries.append(entry)
        self._commands[command_id] = {"digest": command_digest, "outcome": clone(outcome)}
        return clone(outcome)

    def get(self, ref):
        document = self.catalogue.get(ref)
        if self._trusted.get(reference_key(ref)) != digest(document):
            raise GovernanceError("untrusted_record", "Governance record was not issued by this journal instance.")
        return document

    def documents(self, kind=None):
        result = []
        for entry in self._entries:
            for ref in entry["references"]:
                if kind is None or ref["contract_type"] == kind:
                    result.append(self.get(ref))
        return result

    def history(self):
        return clone(self._entries)
