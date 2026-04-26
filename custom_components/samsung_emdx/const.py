"""Constants for the Samsung E-Paper integration."""

from enum import IntEnum, StrEnum
import logging

LOGGER = logging.getLogger(__package__)

DOMAIN = "samsung_emdx"

CONF_MANUFACTURER = "Samsung Electronics"
LOW_POWER_WAKE_PORT = 10194


class Orientation(StrEnum):
    """Physical display orientation."""

    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"


class Rotation(IntEnum):
    """Image rotation angles in degrees."""

    ROTATE_0 = 0
    ROTATE_90 = 90
    ROTATE_180 = 180
    ROTATE_270 = 270


class FitMode(StrEnum):
    """Image fit strategies for mapping source images to display dimensions.

    Controls how aspect ratio mismatches are handled when the source image
    doesn't match the display's pixel dimensions.
    """

    STRETCH = "stretch"  # Distort to fill exact dimensions (ignores aspect ratio)
    CONTAIN = "contain"  # Scale to fit within bounds, pad empty space with white
    COVER = "cover"  # Scale to cover bounds, crop overflow (no distortion)
    CROP = "crop"  # No scaling, center-crop at native resolution (pad if smaller)
