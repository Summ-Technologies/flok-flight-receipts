# importing module
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from pytz import timezone
import pandas as pd

def getTimezone(location: str) -> str:
    # initialize Nominatim API
    geolocator = Nominatim(user_agent="geoapiExercises")
    
    # getting Latitude and Longitude
    coordinates = geolocator.geocode(location)
    if coordinates == None:
        return None
    # pass the Latitude and Longitude
    # into a timezone_at
    # and it return timezone
    obj = TimezoneFinder()
    result = obj.timezone_at(lng=coordinates.longitude, lat=coordinates.latitude)
    return result

def tzDiff(date, zone1, zone2):
    '''
    Returns the difference in seconds between zone1 and zone2
    for a given date.
    '''
    tz1, tz2 = timezone(zone1), timezone(zone2)
    date = pd.to_datetime(date)

    if (tz1.localize(date) > tz2.localize(date).astimezone(tz1)):
        return -(tz1.localize(date) - tz2.localize(date).astimezone(tz1)).seconds
    else:
        return (tz2.localize(date) - tz1.localize(date).astimezone(tz2)).seconds