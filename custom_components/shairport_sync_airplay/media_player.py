"""Media player entity for Shairport Sync via MQTT."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ShairportSyncConfigEntry
from .const import (
    AIRPLAY_VOLUME_MIN,
    AIRPLAY_VOLUME_MUTE,
    ATTR_CLIENT_MODEL,
    ATTR_CLIENT_NAME,
    ATTR_GENRE,
    CMD_DISCONNECT,
    CMD_MUTE_TOGGLE,
    CMD_NEXT,
    CMD_PAUSE,
    CMD_PLAY,
    CMD_PLAY_PAUSE,
    CMD_PREVIOUS,
    CMD_STOP,
    CMD_VOLUME_DOWN,
    CMD_VOLUME_UP,
    CONF_TOPIC,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    TOPIC_ACTIVE,
    TOPIC_ACTIVE_END,
    TOPIC_ACTIVE_START,
    TOPIC_ALBUM,
    TOPIC_ARTIST,
    TOPIC_CLIENT_MODEL,
    TOPIC_CLIENT_NAME,
    TOPIC_COVER,
    TOPIC_GENRE,
    TOPIC_PLAY_END,
    TOPIC_PLAY_RESUME,
    TOPIC_PLAY_START,
    TOPIC_PLAYING,
    TOPIC_REMOTE,
    TOPIC_TITLE,
    TOPIC_TRACK_ID,
    TOPIC_VOLUME,
)

_LOGGER = logging.getLogger(__name__)

# Push-based; no polling and no parallel-update limit needed.
PARALLEL_UPDATES = 0

SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.TURN_OFF
)

# Shairport Sync can substitute empty payloads with a placeholder string
# (mqtt.empty_payload_substitute, "--" in the documented examples).
EMPTY_PAYLOADS: frozenset[str] = frozenset({"", "--"})

# Separator before the status note Spotify appends to the artist field.
ARTIST_SUFFIX_SEPARATOR = " • "


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShairportSyncConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Shairport Sync media player from a config entry."""
    async_add_entities([ShairportSyncMediaPlayer(entry)])


def _text(payload: str | bytes) -> str | None:
    """Return a decoded text payload, or None if it is empty."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    payload = payload.strip()
    return None if payload in EMPTY_PAYLOADS else payload


def _strip_artist_suffix(artist: str | None) -> str | None:
    """Remove a status suffix that some sources append to the artist.

    The Spotify iOS app appends a localized note such as
    " • Video available" / " • Video er tilgængelig" to the artist field it
    hands to AirPlay. The note follows the last " • " separator.
    """
    if artist is None or ARTIST_SUFFIX_SEPARATOR not in artist:
        return artist
    stripped = artist.rsplit(ARTIST_SUFFIX_SEPARATOR, 1)[0].strip()
    return stripped or artist


def _image_content_type(data: bytes) -> str | None:
    """Detect the image type from its magic bytes."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


class ShairportSyncMediaPlayer(MediaPlayerEntity):
    """Representation of a Shairport Sync AirPlay receiver."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_media_content_type = MediaType.MUSIC

    def __init__(self, entry: ShairportSyncConfigEntry) -> None:
        """Initialize the entity."""
        self._topic: str = entry.data[CONF_TOPIC]
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

        self._active = False
        self._playing = False
        self._genre: str | None = None
        self._client_name: str | None = None
        self._client_model: str | None = None
        self._cover: bytes | None = None
        self._cover_type: str | None = None
        self._cover_hash: str | None = None
        self._attr_volume_level = None
        self._attr_is_volume_muted = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Subscribe to the MQTT topics published by Shairport Sync."""
        await super().async_added_to_hass()

        text_handlers: dict[str, Callable[[str | None], None]] = {
            TOPIC_TITLE: self._set_title,
            TOPIC_ARTIST: self._set_artist,
            TOPIC_ALBUM: self._set_album,
            TOPIC_GENRE: self._set_genre,
            TOPIC_TRACK_ID: self._set_track_id,
            TOPIC_CLIENT_NAME: self._set_client_name,
            TOPIC_CLIENT_MODEL: self._set_client_model,
            TOPIC_VOLUME: self._set_volume,
            TOPIC_PLAYING: self._set_playing_flag,
            TOPIC_ACTIVE: self._set_active_flag,
            # Event topics; kept for Shairport Sync builds without the
            # "playing"/"active" flag topics.
            TOPIC_PLAY_START: lambda _: self._set_playing(True),
            TOPIC_PLAY_RESUME: lambda _: self._set_playing(True),
            TOPIC_PLAY_END: lambda _: self._set_playing(False),
            TOPIC_ACTIVE_START: lambda _: self._set_active(True),
            TOPIC_ACTIVE_END: lambda _: self._set_active(False),
        }

        for sub_topic, handler in text_handlers.items():
            self.async_on_remove(
                await mqtt.async_subscribe(
                    self.hass,
                    f"{self._topic}/{sub_topic}",
                    self._make_text_callback(handler),
                )
            )

        # Cover art is binary; subscribe without decoding.
        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass,
                f"{self._topic}/{TOPIC_COVER}",
                self._handle_cover,
                encoding=None,
            )
        )

        self.async_on_remove(
            mqtt.async_subscribe_connection_status(
                self.hass, self._handle_connection_status
            )
        )
        self._attr_available = mqtt.is_connected(self.hass)

    def _make_text_callback(
        self, handler: Callable[[str | None], None]
    ) -> Callable[[mqtt.ReceiveMessage], None]:
        """Wrap a text handler as an MQTT message callback."""

        @callback
        def _message_received(msg: mqtt.ReceiveMessage) -> None:
            handler(_text(msg.payload))
            self.async_write_ha_state()

        return _message_received

    @callback
    def _handle_connection_status(self, connected: bool) -> None:
        """Track MQTT broker connectivity as entity availability."""
        self._attr_available = connected
        self.async_write_ha_state()

    @callback
    def _handle_cover(self, msg: mqtt.ReceiveMessage) -> None:
        """Handle a binary cover art payload."""
        data = msg.payload
        if isinstance(data, str):
            data = data.encode("utf-8", errors="ignore")

        content_type = _image_content_type(data) if data else None
        if content_type is None:
            self._clear_cover()
        else:
            self._cover = data
            self._cover_type = content_type
            self._cover_hash = hashlib.sha256(data).hexdigest()[:16]
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Payload handlers
    # ------------------------------------------------------------------

    def _set_title(self, value: str | None) -> None:
        self._attr_media_title = value

    def _set_artist(self, value: str | None) -> None:
        self._attr_media_artist = _strip_artist_suffix(value)

    def _set_album(self, value: str | None) -> None:
        self._attr_media_album_name = value

    def _set_genre(self, value: str | None) -> None:
        self._genre = value

    def _set_track_id(self, value: str | None) -> None:
        self._attr_media_content_id = value

    def _set_client_name(self, value: str | None) -> None:
        self._client_name = value

    def _set_client_model(self, value: str | None) -> None:
        self._client_model = value

    def _set_playing_flag(self, value: str | None) -> None:
        if value in ("0", "1"):
            self._set_playing(value == "1")

    def _set_active_flag(self, value: str | None) -> None:
        if value in ("0", "1"):
            self._set_active(value == "1")

    def _set_playing(self, playing: bool) -> None:
        self._playing = playing
        if playing:
            self._active = True

    def _set_active(self, active: bool) -> None:
        self._active = active
        if not active:
            self._playing = False
            self._clear_session()

    def _set_volume(self, value: str | None) -> None:
        """Parse 'airplay_volume,volume,lowest_volume,highest_volume'."""
        if value is None:
            return
        try:
            airplay_volume = float(value.split(",", 1)[0])
        except ValueError:
            _LOGGER.debug("Ignoring unparsable volume payload: %s", value)
            return

        if airplay_volume <= AIRPLAY_VOLUME_MUTE:
            self._attr_is_volume_muted = True
            return

        self._attr_is_volume_muted = False
        level = (airplay_volume - AIRPLAY_VOLUME_MIN) / -AIRPLAY_VOLUME_MIN
        self._attr_volume_level = round(min(max(level, 0.0), 1.0), 3)

    def _clear_cover(self) -> None:
        self._cover = None
        self._cover_type = None
        self._cover_hash = None

    def _clear_session(self) -> None:
        """Reset everything that belongs to an AirPlay session."""
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_album_name = None
        self._attr_media_content_id = None
        self._genre = None
        self._client_name = None
        self._client_model = None
        self._clear_cover()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> MediaPlayerState:
        """Return the playback state."""
        if self._playing:
            return MediaPlayerState.PLAYING
        if self._active:
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def media_image_hash(self) -> str | None:
        """Return a hash of the current cover art."""
        return self._cover_hash

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Serve the cover art received over MQTT."""
        return self._cover, self._cover_type

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return AirPlay session details."""
        return {
            ATTR_CLIENT_NAME: self._client_name,
            ATTR_CLIENT_MODEL: self._client_model,
            ATTR_GENRE: self._genre,
        }

    # ------------------------------------------------------------------
    # Commands (DACP via <topic>/remote)
    # ------------------------------------------------------------------

    async def _async_send(self, command: str) -> None:
        await mqtt.async_publish(self.hass, f"{self._topic}/{TOPIC_REMOTE}", command)

    async def async_media_play(self) -> None:
        """Send play command."""
        await self._async_send(CMD_PLAY)

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self._async_send(CMD_PAUSE)

    async def async_media_play_pause(self) -> None:
        """Toggle play/pause on the source."""
        await self._async_send(CMD_PLAY_PAUSE)

    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self._async_send(CMD_STOP)

    async def async_media_next_track(self) -> None:
        """Skip to the next track."""
        await self._async_send(CMD_NEXT)

    async def async_media_previous_track(self) -> None:
        """Go back to the previous track."""
        await self._async_send(CMD_PREVIOUS)

    async def async_volume_up(self) -> None:
        """Ask the source to raise the volume."""
        await self._async_send(CMD_VOLUME_UP)

    async def async_volume_down(self) -> None:
        """Ask the source to lower the volume."""
        await self._async_send(CMD_VOLUME_DOWN)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute. Shairport Sync only exposes a toggle."""
        if self._attr_is_volume_muted is None or self._attr_is_volume_muted != mute:
            await self._async_send(CMD_MUTE_TOGGLE)

    async def async_turn_off(self) -> None:
        """End the current AirPlay session."""
        await self._async_send(CMD_DISCONNECT)
