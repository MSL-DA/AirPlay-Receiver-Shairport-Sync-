"""Config flow for the AirPlay Receiver (Shairport Sync) integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.mqtt import valid_publish_topic, valid_subscribe_topic
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import TextSelector
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo

from .const import (
    CONF_TOPIC,
    DEFAULT_NAME,
    DEFAULT_TOPIC,
    DISCOVERY_MODEL,
    DOMAIN,
    TOPIC_ACTIVE,
    TOPIC_REMOTE,
)

_LOGGER = logging.getLogger(__name__)


def _normalize_topic(topic: str) -> str:
    """Strip whitespace and trailing slashes from a base topic.

    A leading slash is significant in MQTT ("/HiFi" and "HiFi" are different
    topics) and Shairport Sync publishes with it when configured that way, so
    it must be preserved.
    """
    return topic.strip().rstrip("/")


def _validate_topic(topic: str) -> bool:
    """Return True if the base topic can be subscribed to and published under."""
    if not topic or "+" in topic or "#" in topic:
        return False
    try:
        valid_subscribe_topic(f"{topic}/#")
        valid_publish_topic(f"{topic}/{TOPIC_REMOTE}")
    except vol.Invalid:
        return False
    return True


class ShairportSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AirPlay Receiver (Shairport Sync)."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_name: str | None = None
        self._discovered_topic: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            topic = _normalize_topic(user_input[CONF_TOPIC])
            if not _validate_topic(topic):
                errors[CONF_TOPIC] = "invalid_topic"
            else:
                await self.async_set_unique_id(topic)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_TOPIC: topic},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_NAME): TextSelector(),
                        vol.Required(CONF_TOPIC): TextSelector(),
                    }
                ),
                user_input or {CONF_NAME: DEFAULT_NAME, CONF_TOPIC: DEFAULT_TOPIC},
            ),
            errors=errors,
        )

    async def async_step_mqtt(
        self, discovery_info: MqttServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initiated by Shairport Sync's own MQTT discovery."""
        if not discovery_info.payload:
            return self.async_abort(reason="invalid_discovery_info")

        try:
            payload = json.loads(discovery_info.payload)
        except ValueError:
            return self.async_abort(reason="invalid_discovery_info")

        if not isinstance(payload, dict):
            return self.async_abort(reason="invalid_discovery_info")

        device = payload.get("device") or {}
        state_topic = payload.get("state_topic")
        suffix = f"/{TOPIC_ACTIVE}"
        if (
            device.get("model") != DISCOVERY_MODEL
            or not isinstance(state_topic, str)
            or not state_topic.endswith(suffix)
        ):
            return self.async_abort(reason="not_shairport_sync")

        topic = _normalize_topic(state_topic.removesuffix(suffix))
        if not _validate_topic(topic):
            return self.async_abort(reason="invalid_discovery_info")

        await self.async_set_unique_id(topic)
        self._abort_if_unique_id_configured()

        self._discovered_topic = topic
        self._discovered_name = str(device.get("name") or DEFAULT_NAME)
        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered Shairport Sync instance."""
        assert self._discovered_topic is not None
        assert self._discovered_name is not None

        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_TOPIC: self._discovered_topic},
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_NAME): TextSelector()}),
                {CONF_NAME: self._discovered_name},
            ),
            description_placeholders={
                "name": self._discovered_name,
                "topic": self._discovered_topic,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the base topic of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            topic = _normalize_topic(user_input[CONF_TOPIC])
            if not _validate_topic(topic):
                errors[CONF_TOPIC] = "invalid_topic"
            else:
                if topic != entry.unique_id:
                    await self.async_set_unique_id(topic)
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=topic,
                    data_updates={CONF_TOPIC: topic},
                )

        assert self.source == SOURCE_RECONFIGURE
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_TOPIC): TextSelector()}),
                user_input or {CONF_TOPIC: entry.data[CONF_TOPIC]},
            ),
            errors=errors,
        )
