"""Support for controlling multiple media players with a single sensor."""
from __future__ import annotations
from typing import List

import logging

import voluptuous as vol

from homeassistant.components.text import PLATFORM_SCHEMA, TextEntity
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ICON,
    CONF_NAME,
    CONF_UNIQUE_ID,
    CONF_SOURCE,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
    STATE_IDLE,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.reload import async_setup_reload_service

from . import DOMAIN, PLATFORMS
from .const import DEFAULT_BART_STATION
from .bart_api import BartAPIClient

_LOGGER = logging.getLogger(__name__)

ATTR_ACTIVE = "active"
ATTR_AVAILABLE = "available"

CONF_ZONES = "zones"
CONF_SNAP_VOLUME = "snap_volume"
CONF_VOLUME_INCREMENT = "volume_increment"
CONF_VOLUME_MAX = "volume_max"
CONF_VOLUME_MIN = "volume_min"
CONF_COMBINED = "combined"

DEFAULT_NAME = "Bart Zone Media Player"
DEFAULT_COMBINED_NAME = "All Zones"
DEFAULT_COMBINED_ICON = "mdi:speaker-multiple"
DEFAULT_ZONE_NAME = "Zone"
DEFAULT_ICON = "mdi:numeric-{}-box"
DEFAULT_ICON_9_PLUS = "9-plus"

SERVICE_VOLUME_TOGGLE_MUTE = "toggle_volume_mute"
SERVICE_NEXT_ZONE = "next_zone"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ZONES): cv.ensure_list(
            {
                vol.Required(CONF_SOURCE): cv.entity_domain(MEDIA_PLAYER_DOMAIN),
                vol.Optional(CONF_NAME): cv.string,
                vol.Optional(CONF_ICON): cv.icon,
            }
        ),
        vol.Optional(CONF_UNIQUE_ID): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_VOLUME_MAX, default=1.0): vol.Coerce(float),
        vol.Optional(CONF_VOLUME_MIN, default=0.0): vol.Coerce(float),
        vol.Optional(CONF_VOLUME_INCREMENT, default=0.01): vol.Coerce(float),
        vol.Optional(CONF_SNAP_VOLUME, default=False): bool,
        vol.Optional(
            CONF_COMBINED,
            default={
                CONF_NAME: DEFAULT_COMBINED_NAME,
                CONF_ICON: DEFAULT_COMBINED_ICON,
            },
        ): {
            vol.Optional(CONF_NAME, default=DEFAULT_COMBINED_NAME): cv.string,
            vol.Optional(CONF_ICON, default=DEFAULT_COMBINED_ICON): cv.icon,
        },
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the bart zone sensor."""

    unique_id = config.get(CONF_UNIQUE_ID)
    name = config[CONF_NAME]
    volume_min = config[CONF_VOLUME_MIN]
    volume_max = config[CONF_VOLUME_MAX]
    volume_inc = config[CONF_VOLUME_INCREMENT]
    snap = config[CONF_SNAP_VOLUME]

    zones = {}
    for i, zone in enumerate(config[CONF_ZONES]):
        n = i + 1
        zone_name = zone.get(CONF_NAME, f"{DEFAULT_ZONE_NAME} {n}")
        icon_n = str(n) if n < 10 else DEFAULT_ICON_9_PLUS
        icon = zone.get(CONF_ICON, DEFAULT_ICON.format(icon_n))
        entity_id = zone[CONF_SOURCE]

        if entity_id not in zone.keys():
            zones[entity_id] = Zone(zone_name, icon)
        else:
            _LOGGER.warn(
                "Duplicate entity_id '%s' in zone sources, ignoring", entity_id
            )

    all_zones = AllZones(
        list(zones.values()),
        config[CONF_COMBINED][CONF_NAME],
        config[CONF_COMBINED][CONF_ICON],
    )

    bart_api_client = BartAPIClient.get_client(hass, DEFAULT_BART_STATION)

    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    async_add_entities(
        [
            BartZoneSensor(
                unique_id,
                name,
                bart_api_client,
                zones,
                all_zones,
                volume_min,
                volume_max,
                volume_inc,
                snap,
            )
        ]
    )

    # seems unnecessary if I don't register any services
    # platform = entity_platform.async_get_current_platform()


class BartZoneSensor(TextEntity):
    """Representation of a bart zone sensor."""

    def __init__(
        self,
        unique_id: str,
        name: str,
        bart_client,
        zones: dict[str, Zone],
        all_zones: AllZones,
        volume_min: int,
        volume_max: int,
        volume_inc: int,
        snap: bool,
    ):
        self._unique_id = unique_id
        self._name = name
        self._bart_client = bart_client
        self._zones = zones
        self._all_zones = all_zones
        self._volume_min = volume_min
        self._volume_max = volume_max
        self._volume_inc = volume_inc
        self._snap = snap
        self._all_entities = list(self._zones.keys())

        self._current = None
        self._icon = DEFAULT_ICON.format(0)
        self._state = None

    async def async_added_to_hass(self):
        """Handle added to Hass."""

        entity_ids = list(self._zones.keys())

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, entity_ids, self._async_bart_zone_sensor_state_listener
            )
        )

    @property
    def unique_id(self):
        """Return the unique id of this sensor."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        active = []
        available = []
        for entity_id, zone in self._zones.items():
            if zone.active:
                active.append(entity_id)
            if zone.available:
                available.append(entity_id)

        return {
            ATTR_ENTITY_ID: self._all_entities,
            ATTR_ACTIVE: active,
            ATTR_AVAILABLE: available,
        }

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return self._icon

    @callback
    def _async_bart_zone_sensor_state_listener(self, event):
        """Handle media_player state changes."""
        new_state = event.data.get("new_state")
        entity = event.data.get("entity_id")
        _LOGGER.debug("New state from '%s': '%s'", entity, str(new_state))

        zone = self._zones[entity]

        if new_state.state is None:
            self._update_zones(zone, False)
            self.async_write_ha_state()
            return

        self._update_zones(zone, new_state.state in [STATE_ON , STATE_PLAYING, STATE_IDLE])
        self.async_write_ha_state()

    @callback
    def _update_zones(self, zone: Zone, value: bool):
        """Update the active zones."""

        zone.set_active_and_available(value)
        # only 1 zone can be active at a time or all zones.
        if all(
            [z.active == value and z.available == value for z in self._zones.values()]
        ):
            self._all_zones.set_active(value)

            if value:
                # ALL ON
                self._set_current_zone(self._all_zones)
            else:
                # ALL OFF
                self._set_current_zone(None)
        else:
            if value:
                # ONE ON
                self._activate_single_zone(zone)
            else:
                # NEXT ONE
                nxt = self._get_next_zone(zone)
                if nxt is not None:
                    # NEXT ONE ON
                    self._activate_single_zone(nxt)
                else:
                    # ALL OFF
                    self._set_current_zone(None)

    def _get_next_zone(self, current: Zone) -> Zone:
        """Activate the next zone."""
        ret = None
        found = False
        before = None
        after = None
        for zone in self._zones.values():
            if current == zone:
                found = True

            if current != zone and zone.available:
                if found:
                    after = zone
                    break
                elif not found and before is None:
                    before = zone

        if after is not None:
            ret = after
        elif before is not None:
            ret = before

        return ret

    def _activate_single_zone(self, zone) -> None:
        """Activate a single zone, deactivate the rest."""
        # If other zones are active, deactivate them.
        self._set_current_zone(zone)
        for z in self._zones.values():
            if z != zone and z.active and z.available:
                z.set_active(False)

    def _set_current_zone(self, zone: Zone) -> None:
        """Set the current zone."""
        self._current = zone
        if zone is None:
            self._state = STATE_OFF
            self._icon = DEFAULT_ICON.format(0)
        else:
            self._state = zone.name
            self._icon = zone.icon


class Zone(object):
    def __init__(self, name: str, icon: str):
        self._name = name
        self._icon = icon
        self._active = False
        self._available = False

    @property
    def name(self) -> str:
        """Zone name."""
        return self._name

    @property
    def icon(self) -> str:
        """Zone icon."""
        return self._icon

    @property
    def active(self) -> bool:
        """Zone in use."""
        return self._active

    @property
    def available(self) -> bool:
        """Zone available for use."""
        return self._available

    def set_active(self, value: bool) -> None:
        """Set available."""
        self._active = value

    def set_active_and_available(self, value: bool):
        """Set active and available."""
        self.set_active(value)
        self._available = value


class AllZones(Zone):
    def __init__(self, zones: List[Zone], name: str, icon: str):
        super().__init__(name, icon)
        self._zones = zones

    @property
    def active(self) -> bool:
        """Zone in use."""
        if self.available:
            return self._active
        else:
            ret = False
            self._active = ret
            return ret

    @property
    def available(self) -> bool:
        """Zone available for use."""
        return all([z.available for z in self._zones])
