from pydantic import BaseModel

class HourlyWeatherData(BaseModel):
    time: str            # ISO string
    temp: float
    weatherCode: int
    icon: str
    label: str

class WeatherData(BaseModel):
    date: str            # YYYY-MM-DD
    minTemp: float
    maxTemp: float
    weatherCode: int
    icon: str
    label: str
    hourly: list[HourlyWeatherData]
