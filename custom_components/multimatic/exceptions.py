"""Exceptions for multimatic integration."""
from pymultimatic.api import ApiError


class MultimaticError(ApiError):
    """Multimatic error."""
