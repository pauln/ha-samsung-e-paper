"""Service registration for the Samsung E-Paper integration."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
import io
import json
import time
from typing import Any
import uuid

import aiohttp
from anyio import Path
from PIL import Image as PILImage, ImageEnhance, ImageOps
import voluptuous as vol

from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.media_source import async_resolve_media
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url
from homeassistant.helpers.selector import MediaSelector, MediaSelectorConfig

from .const import DOMAIN, LOGGER, FitMode, Orientation, Rotation
from .coordinator import SamsungEMDXConfigEntry

ATTR_IMAGE = "image"
ATTR_ROTATION = "rotation"
ATTR_FIT_MODE = "fit_mode"
ATTR_BRIGHTNESS = "brightness"
ATTR_CONTRAST = "contrast"
ATTR_SATURATION = "saturation"
ATTR_SHARPEN = "sharpen"

# Fill color for CONTAIN and CROP padding (white, natural for e-paper)
_PAD_COLOR = (255, 255, 255)


SCHEMA_UPLOAD_IMAGE = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_IMAGE): MediaSelector(
            MediaSelectorConfig(accept=["image/*"])
        ),
        vol.Optional(ATTR_ROTATION, default=Rotation.ROTATE_0): vol.All(
            vol.Coerce(int), vol.Coerce(Rotation)
        ),
        vol.Optional(ATTR_FIT_MODE, default=FitMode.CONTAIN): vol.In(
            [t.value for t in FitMode]
        ),
        vol.Optional(ATTR_BRIGHTNESS, default=100): vol.All(
            vol.Coerce(int), vol.Clamp(min=0, max=200)
        ),
        vol.Optional(ATTR_CONTRAST, default=100): vol.All(
            vol.Coerce(int), vol.Clamp(min=0, max=300)
        ),
        vol.Optional(ATTR_SATURATION, default=100): vol.All(
            vol.Coerce(int), vol.Clamp(min=0, max=300)
        ),
        vol.Optional(ATTR_SHARPEN, default=0.0): vol.All(
            vol.Coerce(float), vol.Clamp(min=0, max=10)
        ),
    }
)


def _get_entry_for_device(call: ServiceCall) -> SamsungEMDXConfigEntry:
    """Return the config entry for the device targeted by a service call."""
    device_id: str = call.data[ATTR_DEVICE_ID]
    device_registry = dr.async_get(call.hass)
    device = device_registry.async_get(device_id)

    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_device_id",
            translation_placeholders={"device_id": device_id},
        )

    serial_number = next(
        (identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN),
        None,
    )
    if serial_number is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_device_id",
            translation_placeholders={"device_id": device_id},
        )

    entry = call.hass.config_entries.async_entry_for_domain_unique_id(
        DOMAIN, serial_number
    )
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"serial_number": serial_number},
        )

    return entry


def _load_image(path: str) -> PILImage.Image:
    """Load an image from disk and apply EXIF orientation."""
    image = PILImage.open(path)
    image.load()
    return ImageOps.exif_transpose(image)


def _load_image_from_bytes(data: bytes) -> PILImage.Image:
    """Load an image from bytes and apply EXIF orientation."""
    image = PILImage.open(io.BytesIO(data))
    image.load()
    return ImageOps.exif_transpose(image)


async def _async_download_image(hass: HomeAssistant, url: str) -> PILImage.Image:
    """Download an image from a URL and return a PIL Image."""
    if not url.startswith(("http://", "https://")):
        url = get_url(hass) + async_sign_path(
            hass, url, timedelta(minutes=5), use_content_user=True
        )
    session = async_get_clientsession(hass)
    try:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
    except aiohttp.ClientError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="media_download_error",
            translation_placeholders={"error": str(err)},
        ) from err

    return await hass.async_add_executor_job(_load_image_from_bytes, data)


async def _async_upload_image(call: ServiceCall) -> None:
    """Handle the upload_image service call."""
    entry = _get_entry_for_device(call)
    serial_number = entry.unique_id
    assert serial_number is not None

    image_data: dict[str, Any] = call.data[ATTR_IMAGE]

    current = asyncio.current_task()
    if (prev := entry.runtime_data.upload_task) is not None and not prev.done():
        prev.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await prev
    entry.runtime_data.upload_task = current

    try:
        media = await async_resolve_media(
            call.hass, image_data["media_content_id"], None
        )

        if media.path is not None:
            pil_image = await call.hass.async_add_executor_job(
                _load_image, str(media.path)
            )
        else:
            pil_image = await _async_download_image(call.hass, media.url)

        # Wake the device now, so that we can check its configured orientation.
        LOGGER.debug("Attempting to wake device")
        await entry.runtime_data.low_power_wake()

        # Wait a couple of seconds after waking to give device time to settle.
        await asyncio.sleep(2)
        device_orientation = await entry.runtime_data.get_orientation()

        # Apply any/all requested processes to the image.
        pil_image = _prepare_image(pil_image, call.data, device_orientation)

        # Create directory for this device, if it doesn't yet exist.
        path = (
            Path(call.hass.config.config_dir)
            / "www"
            / "samsungemdx"
            / str(serial_number)
        )
        await path.mkdir(parents=True, exist_ok=True)

        base_url = f"{get_url(call.hass)}/local/samsungemdx/{serial_number!s}/"

        # Generate a UUID for this image.
        file_id = str(uuid.uuid4()).upper()
        image_path = path / f"{file_id}.jpg"
        await call.hass.async_add_executor_job(pil_image.save, image_path)
        file_stat = await image_path.stat()
        file_size = file_stat.st_size
        file_path = f"/home/owner/content/Downloads/vxtplayer/epaper/mobile/contents/{file_id}/{file_id}.jpg"
        image_url = f"{base_url}{file_id}.jpg"

        data = {
            "schedule": [
                {
                    "start_date": "1970-01-01",
                    "stop_date": "2999-12-31",
                    "start_time": "00:00:00",
                    "contents": [
                        {
                            "image_url": image_url,
                            "file_id": file_id,
                            "file_path": file_path,
                            "duration": 91326,
                            "file_size": str(file_size),
                            "file_name": f"{file_id}.jpg",
                        },
                    ],
                },
            ],
            "name": "Home Assistant",
            "version": 1,
            "create_time": "2025-01-01 00:00:00",
            "id": file_id,
            "program_id": "com.samsung.ios.ePaper",
            "content_type": "ImageContent",
            "deploy_type": "MOBILE",
        }

        json_content = json.dumps(data, separators=(",", ":")).replace("/", "\\/")

        json_path = path / "content.json"
        await json_path.write_text(json_content)

        json_url = f"{base_url}content.json?ts={time.time_ns()}"
        LOGGER.debug(f"Setting content URL to {json_url}")

        await entry.runtime_data.set_content_download(json_url)

    except asyncio.CancelledError:
        return
    finally:
        if entry.runtime_data.upload_task is current:
            entry.runtime_data.upload_task = None


def _prepare_image(
    image: PILImage.Image,
    params: dict[str, Any] | None,
    device_orientation: Orientation | None,
) -> PILImage.Image:
    """Prepare an image per the provided params."""
    if params is not None:
        brightness: int = params[ATTR_BRIGHTNESS]
        contrast: int = params[ATTR_CONTRAST]
        saturation: int = params[ATTR_SATURATION]
        sharpen: float = params[ATTR_SHARPEN]
        rotation: Rotation = params[ATTR_ROTATION]
        fit_mode: FitMode = params[ATTR_FIT_MODE]

        if brightness != 100:
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(float(brightness) / 100)

        if contrast != 100:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(float(contrast) / 100)

        if saturation != 100:
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(float(saturation) / 100)

        if sharpen > 0.0:
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(sharpen)

        if rotation != Rotation.ROTATE_0:
            image = _rotate_source_image(image, rotation)

        if fit_mode != FitMode.CONTAIN:
            target_size = (2560, 1440)
            if device_orientation == Orientation.PORTRAIT:
                target_size = (1440, 2560)

            if image.size != target_size:
                image = _fit_image(image, target_size, fit_mode)

    return image


def _rotate_source_image(image: PILImage.Image, rotate: Rotation) -> PILImage.Image:
    """Applies the requested rotation to an image."""
    if not isinstance(rotate, Rotation):
        raise TypeError(f"rotate must be Rotation, got {type(rotate).__name__}")

    if rotate == Rotation.ROTATE_0:
        return image
    if rotate == Rotation.ROTATE_90:
        return image.transpose(PILImage.Transpose.ROTATE_90)
    if rotate == Rotation.ROTATE_180:
        return image.transpose(PILImage.Transpose.ROTATE_180)
    if rotate == Rotation.ROTATE_270:
        return image.transpose(PILImage.Transpose.ROTATE_270)
    return image


def _fit_image(
    image: PILImage.Image,
    target_size: tuple[int, int],
    fit: FitMode,
) -> PILImage.Image:
    """Fit an image to target dimensions using the specified strategy.

    Args:
        image: Source PIL Image
        target_size: (width, height) of the display
        fit: Fit strategy to apply

    Returns:
        Image with exact target dimensions
    """
    if fit == FitMode.STRETCH:
        return image.resize(target_size, PILImage.Resampling.LANCZOS)

    if fit == FitMode.CONTAIN:
        return ImageOps.pad(
            image, target_size, PILImage.Resampling.LANCZOS, color=_PAD_COLOR
        )

    if fit == FitMode.COVER:
        return ImageOps.fit(image, target_size, PILImage.Resampling.LANCZOS)

    if fit == FitMode.CROP:
        tw, th = target_size
        sw, sh = image.size

        # Crop region from source (centered, clamped to target size)
        crop_w, crop_h = min(sw, tw), min(sh, th)
        left = (sw - crop_w) // 2
        top = (sh - crop_h) // 2
        cropped = image.crop((left, top, left + crop_w, top + crop_h))

        # Paste centered onto white canvas if padding needed
        if crop_w == tw and crop_h == th:
            return cropped
        canvas = PILImage.new("RGB", target_size, _PAD_COLOR)
        paste_x = (tw - crop_w) // 2
        paste_y = (th - crop_h) // 2
        canvas.paste(cropped, (paste_x, paste_y))
        return canvas

    raise ValueError(f"Unknown fit mode: {fit}")


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register Samsung E-Paper services."""
    hass.services.async_register(
        DOMAIN,
        "upload_image",
        _async_upload_image,
        schema=SCHEMA_UPLOAD_IMAGE,
    )
