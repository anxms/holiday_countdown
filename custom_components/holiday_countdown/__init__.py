from .const import DOMAIN

async def async_setup_entry(hass, config_entry):
    await hass.config_entries.async_forward_entry_setups(config_entry, ["sensor"])
    return True

async def async_unload_entry(hass, config_entry):
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, ["sensor"])
    return unload_ok
