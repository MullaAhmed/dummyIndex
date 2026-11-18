"""Errors for the required-setup manifest (``.context/config.toml``)."""


class RequirementsError(Exception):
    """``config.toml`` is malformed, unsupported, or cannot be edited in place."""
