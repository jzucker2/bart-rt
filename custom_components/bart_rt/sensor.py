"""Support for controlling multiple media players with a single sensor."""
from __future__ import annotations
from typing import List
from enum import Enum

import logging

import voluptuous as vol

from homeassistant.components.text import PLATFORM_SCHEMA, TextEntity
from homeassistant.const import (
    CONF_ICON,
    CONF_NAME,
    CONF_UNIQUE_ID,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import DOMAIN
from .const import DEFAULT_BART_STATION
from .bart_api import BartAPIClient

_LOGGER = logging.getLogger(__name__)


DEFAULT_NAME = "Bart Train Line Sensor"
DEFAULT_ICON = "mdi:numeric-{}-box"


SCAN_INTERVAL = 60

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_UNIQUE_ID): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the bart train line sensor."""

    bart_api_client = BartAPIClient.get_client(hass, DEFAULT_BART_STATION)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        # Name of the data. For logging purposes.
        name=DOMAIN,
        update_method=bart_api_client.async_update,
        # update_method=eshop.fetch_on_sale,
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=SCAN_INTERVAL,
    )

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_refresh()

    # await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    async_add_entities(
        [
            BartTrainSensor(
                coordinator,
                bts.friendly_name
            )
            for bts in BartTrainLines.get_all_train_lines()
        ]
    )

    # seems unnecessary if I don't register any services
    # platform = entity_platform.async_get_current_platform()


class BartTrainSensor(CoordinatorEntity, TextEntity):
    """Representation of a bart train text sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        name: str,
    ):
        super().__init__(coordinator)
        self._name = name

        self._icon = DEFAULT_ICON.format(0)
        self._state = None

    # async def async_added_to_hass(self):
    #     """Handle added to Hass."""
    #
    #     entity_ids = list(self._zones.keys())
    #
    #     self.async_on_remove(
    #         async_track_state_change_event(
    #             self.hass, entity_ids, self._async_bart_zone_sensor_state_listener
    #         )
    #     )

    # @property
    # def unique_id(self):
    #     """Return the unique id of this sensor."""
    #     return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    # @property
    # def should_poll(self):
    #     """No polling needed."""
    #     return False

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return self._icon


class BartTrainLinesException(Exception):
    pass


class BartTrainLines(Enum):
    ANTIOCH = 'Antioch'
    DALY_CITY = 'Daly City'
    DUBLIN_PLEASANTON = 'Dublin/Pleasanton'
    MILLBRAE = 'Millbrae'
    RICHMOND = 'Richmond'
    SF_AIRPORT = 'SF Airport'
    SFO_MILLBRAE = 'SFO/Millbrae'
    PITTSBURG_BAY_POINT = 'Pittsburg/Bay Point'
    BERRYESSA = 'Berryessa'

    @property
    def friendly_name(self):
        return self.value

    @property
    def abbreviation(self):
        if self == self.ANTIOCH:
            return 'ANTC'
        elif self == self.DALY_CITY:
            return 'DALY'
        elif self == self.DUBLIN_PLEASANTON:
            return 'DUBL'
        elif self == self.MILLBRAE:
            return 'MLBR'
        elif self == self.RICHMOND:
            return 'RICH'
        elif self == self.SF_AIRPORT:
            return 'SFIA'
        elif self == self.SFO_MILLBRAE:
            return 'MLBR'
        elif self == self.PITTSBURG_BAY_POINT:
            return 'PITT'
        elif self == self.BERRYESSA:
            return 'BERY'
        raise BartTrainLinesException(f'unknown abbr for type self: {self}')

    @classmethod
    def get_all_train_lines(cls):
        # could I also do `list(cls)`?
        return list(BartTrainLines)
