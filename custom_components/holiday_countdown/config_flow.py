import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN

class HolidayCountdownFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
            
        return self.async_create_entry(
            title="节假日倒计时",
            data={} 
        )