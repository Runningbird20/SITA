class LLMTimeoutError(Exception):
    """Raised by a provider's _complete() when the call times out."""


class LLMProviderError(Exception):
    """Raised by a provider's _complete() for any other connection/HTTP
    failure.
    """
