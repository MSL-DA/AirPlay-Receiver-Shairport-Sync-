# AirPlay Receiver (Shairport Sync) for Home Assistant

A custom integration that turns one or more [Shairport Sync](https://github.com/mikebrady/shairport-sync)
AirPlay receivers into Home Assistant `media_player` entities, using Shairport Sync's built-in MQTT
interface through Home Assistant's existing MQTT integration.

Each Shairport Sync instance becomes one device with one media player entity showing:

- Playback state (`playing`, `paused`, `idle`)
- Title, artist, album and genre
- Cover art (served through Home Assistant's media image proxy, so it works remotely and in the app)
- AirPlay volume and mute state
- The connected AirPlay client (`client_name`, `client_model` attributes)

Playback commands (play, pause, stop, next, previous, volume up/down, mute, disconnect) are sent to
`<topic>/remote`.

## Requirements

- Home Assistant 2026.3 or newer, with the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/)
  set up against the same broker Shairport Sync publishes to.
- Shairport Sync built with `--with-mqtt-client` and `--with-metadata` (the official Docker image has
  MQTT enabled). `shairport-sync -V` must include `mqtt`.

Written against the MQTT interface of Shairport Sync 5.6 (`mqtt.c`): parsed topics, the `active` and
`playing` flag topics, remote commands and the Home Assistant discovery payload format. Older builds
that only publish the `play_start`/`play_end`/`active_start`/`active_end` event topics are also
handled.

## Shairport Sync configuration

Give every instance its own, unique base topic. The base topic is what identifies the instance in
Home Assistant.

```conf
general =
{
	name = "Living Room";
};

metadata =
{
	enabled = "yes";
	include_cover_art = "yes";
};

mqtt =
{
	enabled = "yes";
	hostname = "mqtt-broker.example";
	port = 1883;
	username = "shairport";
	password = "secret";
	topic = "airplay/livingroom";   // unique per instance
	publish_parsed = "yes";         // required: title, artist, album, playing, active, volume ...
	publish_cover = "yes";          // cover art
	enable_remote = "yes";          // required for playback control
//	enable_autodiscovery = "yes";   // optional: lets Home Assistant discover the instance (see below)
//	publish_retain = "yes";         // optional: Home Assistant gets current state after a restart
};
```

### Notes

- `publish_retain = "yes"` lets Home Assistant pick up the last known track and state immediately after
  a restart. The trade-off is that a retained `playing = 1` can be stale if Shairport Sync stops
  uncleanly.
- Remote control uses DACP. It only works when the AirPlay source supports it (for example the Music
  app on iOS/macOS). Volume and mute commands ask the *source* to change volume; Shairport Sync only
  exposes a mute toggle, so `volume_mute` sends `mutetoggle` only when the requested state differs from
  the reported one.
- Turning the entity off sends `disconnect`, which ends the current AirPlay session.

## Installation

### HACS (custom repository)

1. HACS → three-dot menu → **Custom repositories** → add this repository's URL as type **Integration**.
2. Install **AirPlay Receiver (Shairport Sync)** and restart Home Assistant.

### Manual

Copy `custom_components/shairport_sync_airplay` to `<config>/custom_components/shairport_sync_airplay` and
restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → AirPlay Receiver (Shairport Sync)**, then enter a name and the
base topic (e.g. `airplay/livingroom`). Repeat for each instance.

### Discovery

If `enable_autodiscovery = "yes"` is set in Shairport Sync and the default discovery prefix
(`homeassistant`) is used, each instance is offered automatically under **Discovered**. Shairport Sync's
own discovery also creates separate MQTT sensors; those are independent of this integration and can
be disabled if not needed.

## Dashboard cards

The entity works with the standard cards; no custom frontend code is required.

Media control card:

```yaml
type: media-control
entity: media_player.living_room
```

Tile card with playback and volume controls:

```yaml
type: tile
entity: media_player.living_room
features:
  - type: media-player-playback
  - type: media-player-volume-buttons
    show_mute_button: true
```

`media-player-volume-buttons` is used rather than the slider because AirPlay volume is controlled by
the source; Home Assistant can step it, but not set an absolute level.

## Troubleshooting

```yaml
logger:
  logs:
    custom_components.shairport_sync_airplay: debug
```

Use **Settings → Devices & services → MQTT → Configure → Listen to a topic** with
`airplay/livingroom/#` to check what Shairport Sync is actually publishing.
