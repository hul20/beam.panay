"""Errors suitable for display without a Python traceback."""


class PipelineError(Exception):
    """A source, configuration, or output prevented the requested stage."""
