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


class UnauthorizedError(Exception):
    """Raised by app.auth.deps.get_current_user when auth is enabled (at
    least one User exists) and the request has no valid session token. See
    DEF.md § Phase 14, "Multi-user / RBAC (post-roadmap)".
    """

    def __init__(self, message: str = "Missing or invalid session token"):
        self.message = message
        super().__init__(message)


class ForbiddenError(Exception):
    """Raised by app.auth.deps.require_admin — a valid, authenticated user
    whose role doesn't permit the action (distinct from UnauthorizedError:
    this is "I know who you are, but no").
    """

    def __init__(self, message: str = "This action requires the admin role"):
        self.message = message
        super().__init__(message)
