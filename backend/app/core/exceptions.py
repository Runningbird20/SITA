"""Application-level exceptions mapped to a consistent JSON error envelope
by handlers registered in app.main. See DEF.md § Phase 9.
"""


class NotFoundError(Exception):
    def __init__(self, resource: str, identifier: object):
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} {identifier} not found")


class InvalidQueryParameterError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
