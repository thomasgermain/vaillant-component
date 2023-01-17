"""Config flow for multimatic integration."""
import logging

from pymultimatic.api import ApiError, defaults
from pymultimatic.systemmanager import SystemManager
import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv

from .const import CONF_SERIAL_NUMBER, DEFAULT_SCAN_INTERVAL, DOMAIN, CONF_APPLICATION

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SERIAL_NUMBER): str,
        vol.Required(CONF_APPLICATION, default="MULTIMATIC"): vol.In(["MULTIMATIC", "SENSO"]),
    }
)


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """

    await validate_authentication(hass, data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_APPLICATION])

    return {"title": "Multimatic"}


async def validate_authentication(hass, username, password, application):
    """Ensure provided credentials are working."""
    try:
        systemApplication = defaults.SENSO if application == "SENSO" else defaults.MULTIMATIC
        if not await SystemManager(
            user=username,
            password=password,
            session=async_create_clientsession(hass),
            application=systemApplication,
        ).login(True):
            raise InvalidAuth
    except ApiError as err:
        _LOGGER.error(
            "Unable to authenticate: %s, status: %s, response: %s",
            err.message,
            err.status,
            err.response,
        )
        raise InvalidAuth from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for multimatic."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return MultimaticOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class MultimaticOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): cv.positive_int
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
