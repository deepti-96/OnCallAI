class IncidentProcessingError(Exception):
    """Base class for incident workflow failures."""


class RetryableIncidentError(IncidentProcessingError):
    """Raised when the worker should retry the incident later."""


class TerminalIncidentError(IncidentProcessingError):
    """Raised when the worker should stop retrying and dead-letter the incident."""
