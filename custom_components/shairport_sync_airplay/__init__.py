"""The AirPlay Receiver (Shairport Sync) integration."""

from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

type ShairportSyncConfigEntry = ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: ShairportSyncConfigEntry
) -> bool:
    """Set up AirPlay Receiver (Shairport Sync) from a config entry."""
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="mqtt_not_available",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ShairportSyncConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
