from __future__ import annotations


import logging
import httpx
import xmltodict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import create_async_httpx_client
from homeassistant.helpers.json import json_dumps

from .const import XML_MIME_TYPES, DEFAULT_ENCODING

DEFAULT_TIMEOUT = 10

_LOGGER = logging.getLogger(__name__)


class BartAPIClient:
    """Class for handling the BartAPIClient data retrieval."""

    def __init__(
        self,
        hass: HomeAssistant,
        station: str | None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the data object."""
        self._hass = hass
        self._auth = None
        self._station = station
        self._timeout = timeout
        self._verify_ssl = False
        self._method = "GET"
        self._encoding = DEFAULT_ENCODING
        self._async_client: httpx.AsyncClient | None = None
        self.data: str | None = None
        self.last_exception: Exception | None = None
        self.headers: httpx.Headers | None = None

    @classmethod
    def get_client(
            cls,
            hass: HomeAssistant,
            station: str | None,
            timeout: int = DEFAULT_TIMEOUT,
    ) -> BartAPIClient:
        return cls(hass, station, timeout=timeout)

    @property
    def station(self):
        return self._station

    @property
    def base_url(self):
        return 'test'

    def set_payload(self, payload: str) -> None:
        """Set request data."""
        self._request_data = payload

    def data_without_xml(self) -> str | None:
        """If the data is an XML string, convert it to a JSON string."""
        _LOGGER.debug("Data fetched from resource: %s", self.data)
        if (
            (value := self.data) is not None
            # If the http request failed, headers will be None
            and (headers := self.headers) is not None
            and (content_type := headers.get("content-type"))
            and content_type.startswith(XML_MIME_TYPES)
        ):
            value = json_dumps(xmltodict.parse(value))
            _LOGGER.debug("JSON converted from XML: %s", value)
        return value

    async def async_update(self, log_errors: bool = True) -> None:
        """Get the latest data from REST service with provided method."""
        if not self._async_client:
            self._async_client = create_async_httpx_client(
                self._hass,
                verify_ssl=self._verify_ssl,
                default_encoding=self._encoding,
            )

        # rendered_headers = template.render_complex(self._headers, parse_result=False)
        # rendered_params = template.render_complex(self._params)

        _LOGGER.debug("Updating from %s", self.base_url)
        try:
            response = await self._async_client.request(
                self._method,
                self.base_url,
                # headers=rendered_headers,
                # params=rendered_params,
                # auth=self._auth,
                # content=self._request_data,
                timeout=self._timeout,
                follow_redirects=True,
            )
            self.data = response.text
            self.headers = response.headers
        except httpx.TimeoutException as ex:
            if log_errors:
                _LOGGER.error("Timeout while fetching data: %s", self.base_url)
            self.last_exception = ex
            self.data = None
            self.headers = None
        except httpx.RequestError as ex:
            if log_errors:
                _LOGGER.error(
                    "Error fetching data: %s failed with %s", self.base_url, ex
                )
            self.last_exception = ex
            self.data = None
            self.headers = None
        except Exception as unexp:
            if log_errors:
                _LOGGER.error(
                    "Error fetching data: %s failed with %s", self.base_url, unexp
                )
            self.last_exception = unexp
            self.data = None
            self.headers = None
        # except ssl.SSLError as ex:
        #     if log_errors:
        #         _LOGGER.error(
        #             "Error connecting to %s failed with %s", self._resource, ex
        #         )
        #     self.last_exception = ex
        #     self.data = None
        #     self.headers = None
