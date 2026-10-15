"""Constants for the AirPlay Receiver (Shairport Sync) integration."""

from typing import Final

DOMAIN: Final = "shairport_sync_airplay"

CONF_TOPIC: Final = "topic"

DEFAULT_NAME: Final = "Shairport Sync"
DEFAULT_TOPIC: Final = "shairport"

MANUFACTURER: Final = "Mike Brady"
MODEL: Final = "Shairport Sync"

# Model string Shairport Sync uses in its own MQTT discovery payloads.
DISCOVERY_MODEL: Final = "Shairport Sync"

# Parsed sub-topics published by Shairport Sync (relative to the base topic).
TOPIC_TITLE: Final = "title"
TOPIC_ARTIST: Final = "artist"
TOPIC_ALBUM: Final = "album"
TOPIC_GENRE: Final = "genre"
TOPIC_TRACK_ID: Final = "track_id"
TOPIC_COVER: Final = "cover"
TOPIC_VOLUME: Final = "volume"
TOPIC_CLIENT_NAME: Final = "client_name"
TOPIC_CLIENT_MODEL: Final = "client_model"
TOPIC_PLAYING: Final = "playing"
TOPIC_ACTIVE: Final = "active"
TOPIC_PLAY_START: Final = "play_start"
TOPIC_PLAY_END: Final = "play_end"
TOPIC_PLAY_RESUME: Final = "play_resume"
TOPIC_ACTIVE_START: Final = "active_start"
TOPIC_ACTIVE_END: Final = "active_end"
TOPIC_REMOTE: Final = "remote"

# Commands accepted on <topic>/remote (see mqtt.c in Shairport Sync).
CMD_PLAY: Final = "play"
CMD_PAUSE: Final = "pause"
CMD_PLAY_PAUSE: Final = "playpause"
CMD_STOP: Final = "stop"
CMD_NEXT: Final = "nextitem"
CMD_PREVIOUS: Final = "previtem"
CMD_VOLUME_UP: Final = "volumeup"
CMD_VOLUME_DOWN: Final = "volumedown"
CMD_MUTE_TOGGLE: Final = "mutetoggle"
CMD_DISCONNECT: Final = "disconnect"

# AirPlay volume range: 0.0 (max) down to -30.0 (min); -144.0 means mute.
AIRPLAY_VOLUME_MIN: Final = -30.0
AIRPLAY_VOLUME_MUTE: Final = -144.0

ATTR_CLIENT_NAME: Final = "client_name"
ATTR_CLIENT_MODEL: Final = "client_model"
ATTR_GENRE: Final = "genre"
