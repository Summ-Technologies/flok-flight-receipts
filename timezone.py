# importing module
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from pytz import timezone
import pandas as pd

def getTimezone(location: str) -> str:
    # initialize Nominatim API
    geolocator = Nominatim(user_agent="geoapiExercises")
    
    # getting Latitude and Longitude
    location = geolocator.geocode(location)

    # pass the Latitude and Longitude
    # into a timezone_at
    # and it return timezone
    obj = TimezoneFinder()
    result = obj.timezone_at(lng=location.longitude, lat=location.latitude)
    return result

def tzDiff(date, tz1, tz2):
    '''
    Returns the difference in hours between timezone1 and timezone2
    for a given date.
    '''
    tz1, tz2 = timezone(tz1), timezone(tz2)
    date = pd.to_datetime(date)

    if (tz1.localize(date) > tz2.localize(date).astimezone(tz1)):
        return (tz1.localize(date) - tz2.localize(date).astimezone(tz1)).seconds
    else:
        return (tz2.localize(date) - tz1.localize(date).astimezone(tz2)).seconds