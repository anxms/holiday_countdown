import logging
import datetime
import homeassistant.util.dt as dt_util
from homeassistant.helpers.entity import Entity
from homeassistant.helpers import storage
from homeassistant.util import Throttle
import aiohttp
from .const import (
    DOMAIN,
    DATA_CACHE_KEY,
    ATTRIBUTES
)

_LOGGER = logging.getLogger(__name__)
MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(hours=6)

class HolidayCountdownSensor(Entity):
    def __init__(self, hass):
        self._hass = hass
        self._state = None
        self._attributes = {
            ATTRIBUTES['name']: "加载中...",
            ATTRIBUTES['days']: None,
            ATTRIBUTES['countdown']: None,
            ATTRIBUTES['date']: None,
            ATTRIBUTES['next']: None
        }
        self._unique_id = "holiday_countdown_cn"
        self._store = storage.Store(hass, 1, DATA_CACHE_KEY)
        self._last_updated = None
        self._holidays = []

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return "节假日倒计时"

    @property
    def state(self):
        return self._state

    @property
    def icon(self):
        return "mdi:calendar-star"

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_added_to_hass(self):
        await self._load_cached_data()
        if not self._holidays:
            await self._update_holiday_data()
        else:
            self._process_next_holiday()
    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        await self._update_holiday_data()
    
    async def _load_cached_data(self):
        try:
            cached_data = await self._store.async_load()
            if cached_data and isinstance(cached_data, dict):
                self._holidays = []
                for holiday_data in cached_data.get('holidays', []):
                    try:
                        date = datetime.datetime.fromisoformat(holiday_data['date']).date()
                        self._holidays.append({
                            'date': date,
                            'name': holiday_data['name'],
                            'duration': holiday_data['duration']
                        })
                    except Exception as e:
                        _LOGGER.error("加载节假日数据失败: %s", e)
                
                last_updated_str = cached_data.get('last_updated')
                if last_updated_str:
                    self._last_updated = dt_util.as_local(dt_util.parse_datetime(last_updated_str))
                
                _LOGGER.debug("已加载缓存数据：%s 个节假日", len(self._holidays))
                
                if self._holidays:
                    self._process_next_holiday()
        except Exception as e:
            _LOGGER.error("加载缓存数据失败: %s", e)
    
    async def _update_holiday_data(self):
        """更新节假日数据"""
        try:
            now = dt_util.now()
            current_year = now.year
            
            need_update = not self._last_updated or now.date() > self._last_updated.date()
            if self._last_updated and (now.date() - self._last_updated.date()).days > 30:
                need_update = True
            
            if need_update:
                _LOGGER.debug("需要更新节假日数据")
                
                url = f"https://timor.tech/api/holiday/year/{current_year}"
                _LOGGER.debug("请求URL: %s", url)
                
                try:
                    headers = {'User-Agent': 'HomeAssistant/1.0'}
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers, timeout=8) as response:
                            response.raise_for_status()
                            data = await response.json()
                            
                            if data.get('code') == 0:
                                self._holidays = self._parse_holiday_data(data.get('holiday', {}), current_year)
                                _LOGGER.info("获取 %d 年节假日成功，共 %d 个节假日", current_year, len(self._holidays))
                                
                                await self._store.async_save({
                                    'holidays': [{
                                        'date': holiday['date'].isoformat(),
                                        'name': holiday['name'],
                                        'duration': holiday['duration']
                                    } for holiday in self._holidays],
                                    'last_updated': now.isoformat()
                                })
                                self._last_updated = now
                                _LOGGER.info("节假日数据已缓存")
                                
                                self._process_next_holiday()
                            else:
                                _LOGGER.error("API返回错误: %s", data.get('msg', '未知错误'))
                except Exception as e:
                    _LOGGER.error("获取节假日数据失败: %s", e)
        except Exception as e:
            _LOGGER.error("更新节假日数据出错: %s", e, exc_info=True)
            self._state = "错误"
            self._attributes[ATTRIBUTES['name']] = f"错误: {str(e)}"
    
    def _parse_holiday_data(self, holiday_data, year):
        """解析节假日数据，自动补全年份"""
        holidays = []
        today = dt_util.now().date()
        
        for date_str, info in holiday_data.items():
            try:
                if info.get('holiday'):
                    if '-' in date_str:
                        parts = date_str.split('-')
                        if len(parts) == 2:
                            date_str = f"{year}-{date_str}"
                        elif len(parts) == 3 and len(parts[0]) != 4:
                            date_str = f"{year}-{parts[1]}-{parts[2]}"
                    
                    date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    
                    if (date_obj - today).days >= -30:
                        holidays.append({
                            'date': date_obj,
                            'name': info.get('name', '未知节日'),
                            'original_name': info.get('name', '未知节日')
                        })
            except Exception as e:
                _LOGGER.warning("解析节假日 '%s' 失败: %s", date_str, e)
        
        grouped = {}
        for holiday in holidays:
            base_name = self._get_base_holiday_name(holiday['name'])
            if base_name not in grouped:
                grouped[base_name] = []
            grouped[base_name].append(holiday)
        
        result = []
        for base_name, items in grouped.items():
            sorted_dates = sorted(items, key=lambda x: x['date'])
            result.append({
                'name': base_name,
                'date': sorted_dates[0]['date'],
                'duration': len(sorted_dates),
                'all_dates': sorted_dates
            })
        
        return sorted(result, key=lambda x: x['date'])
    
    def _get_base_holiday_name(self, name):
        for suffix in ["(1月", "(2月", "(3月", "(4月", "(5月", "(6月", 
                     "(7月", "(8月", "(9月", "(10月", "(11月", "(12月"]:
            pos = name.find(suffix)
            if pos > 0:
                return name[:pos].strip()
        return name
    
    def _process_next_holiday(self):
        try:
            today = dt_util.now().date()
            next_holiday = None
            
            for holiday in self._holidays:
                if holiday['date'] >= today:
                    next_holiday = holiday
                    break
            
            if next_holiday:
                days_left = (next_holiday['date'] - today).days
                
                self._state = days_left
                self._attributes = {
                    ATTRIBUTES['name']: next_holiday['name'],
                    ATTRIBUTES['days']: next_holiday['duration'],
                    ATTRIBUTES['countdown']: days_left,
                    ATTRIBUTES['date']: next_holiday['date'].isoformat(),
                    ATTRIBUTES['next']: self._get_next_holiday(next_holiday) or "无"
                }
            else:
                self._state = 0
                self._attributes = {
                    ATTRIBUTES['name']: "今年无更多节假日",
                    ATTRIBUTES['days']: 0,
                    ATTRIBUTES['countdown']: 0,
                    ATTRIBUTES['date']: None,
                    ATTRIBUTES['next']: None
                }
        except Exception as e:
            _LOGGER.error("处理节假日数据失败: %s", e, exc_info=True)
            self._state = "数据处理错误"
            self._attributes[ATTRIBUTES['name']] = f"处理错误: {str(e)}"
    
    def _get_next_holiday(self, current_holiday):
        try:
            current_date = current_holiday['date']
            for holiday in self._holidays:
                if holiday['date'] > current_date:
                    return holiday['name']
        except:
            pass
        return None

async def async_setup_entry(hass, config_entry, async_add_entities):
    sensor = HolidayCountdownSensor(hass)
    async_add_entities([sensor], True)