"""Weather lookup tool with fallback when unconfigured."""

from typing import Any

import httpx

from medicare.config import settings
from medicare.tools.base import BaseTool


class WeatherTool(BaseTool):
    """Tool for checking real-time weather reports."""

    name = "weather"
    description = "Retrieve real-time weather reports and forecasts for a specified geographic city or region."

    async def execute(self, location: str = "", **kwargs: Any) -> str:
        if not location:
            return "Error: Missing location parameter."

        api_key = settings.OPENWEATHER_API_KEY
        if not api_key:
            # Graceful simulation fallback
            return f"Weather report for {location}: 22°C (71°F), Partly Cloudy, Humidity 55%, Wind 8 km/h (Simulated)."

        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    temp = data["main"]["temp"]
                    desc = data["weather"][0]["description"]
                    return f"Weather for {location}: {temp}°C, {desc}."
                return f"Unable to fetch weather for {location} (HTTP {resp.status_code})."
        except Exception as err:
            return f"Weather lookup failed: {err}"
