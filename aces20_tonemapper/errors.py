"""Exception types shared across the package."""


class TonemapError(Exception):
    """Base class for all expected, user-facing errors."""


class ConfigError(TonemapError):
    """The OpenColorIO configuration, color space, display or view is invalid."""


class ImageReadError(TonemapError):
    """An input image could not be decoded into an RGB float matrix."""
