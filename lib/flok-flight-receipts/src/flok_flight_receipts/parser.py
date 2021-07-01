from __future__ import print_function

import enum
import operator
import os.path
import pickle
import re
import time
from base64 import urlsafe_b64decode as decode
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pytz import utc

from .timezone import getTimezone, tzDiff

# If modifying these scopes, delete the file token.pickle.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# user
_userId = "testflok0@gmail.com"

curr_file_dir = os.path.dirname(os.path.realpath(__file__))


def main():

    # fetching from gmail API
    service = createService()
    messages = fetchEmailList(service)
    parts = fetchEmailHtml(service, messages)

    # processing
    airport_codes = pickle.load(open(_data_file("airport_codes.pickle"), "rb"))
    airline_codes = pickle.load(open(_data_file("airline_codes.pickle"), "rb"))
    
    emails = [preprocess(p) for p in parts]

    infos = []
    for i, email in enumerate(emails):
        print(i + 1)
        info = parse(email, airport_codes, airline_codes)
        infos.append(info)
        print("\n")

    return infos

def local(): 
    parts = pickle.load(open(_data_file("parts.pickle"), "rb"))
    airport_codes = pickle.load(open(_data_file("airport_codes.pickle"), "rb"))
    airline_codes = pickle.load(open(_data_file("airline_codes.pickle"), "rb"))    
    emails = [preprocess(p) for p in parts]

    infos = []
    for i, email in enumerate(emails):
        print(i + 1)
        info = parse(email, airport_codes, airline_codes)
        infos.append(info)
        print("\n")

    return infos


def parse(email, airport_codes, airline_codes, threshold=0) -> None:
    """
    Prints summary of parsed email.

            Params:
                        email (list[str]):   list of all words in the email
                        aiport_codes (dict[str,str]):    map from airport code to name
                        airline_codes (dict[str,str]):    map from airline code to name
            Returns:
                        None
    """
    cost, confirmation, name = None, None, None
    counter = dict()
    airports, flights = [], []
    arr_dates, arr_times, dep_dates, dep_times, durations = [], [], [], [], []

    da_flag = True  # alternates b/w appending to dep_time or arr_time
    err_flag = False  # set if potential parsing errors

    heuristics = {
        'confirmation': ['record locator:','confirmation code is', 'confirmation code', 'confirmation code:', 'confirmation number:', 'confirmation #:', 'confirmation #', 'booking code:', 'booking reference'],
        'name': ['hi','name:','traveler details','travelers','passenger','passenger:'],
    }

    for i in range(len(email)):
        current_lower = email[i].lower()
        # find flights
        if i + 2 < len(email):
            flight = follows(email, i, ['flight #'])
            if flight != None:
                flights.append(flight)
            elif (current_lower in airline_codes or current_lower in {'flight'}) \
                and bool(re.match("^([1-9][0-9]{1,3})$", email[i+1])):
                flights.append(email[i] + " " + email[i+1])
            else:
                chars, nums = splitCharDig(email[i])
                if chars != None and chars.lower() in airline_codes and bool(re.match("^([1-9][0-9]{1,3})$", nums)):
                    flights.append(chars + " " + nums)
            
        # find times
        if isValidTime(email, i):
            time = current_lower
            if 'am' in time:
                time = time[:time.find('am')] + " AM" 
            elif 'pm' in time:
                time = time[:time.find('pm')] + " PM"
            elif i < len(email) - 1 and email[i+1].lower() in ['am', 'pm']:
                time = email[i] + " " + email[i+1]

            if da_flag:
                dep_times.append(time)
            else:
                arr_times.append(time)
            da_flag = not da_flag
        
        # find dates
        date = isValidDate(email, i)
        if date != None:
            dep_dates.append(date)
        # assigns dateless flights to most recent date
        elif len(dep_dates) < len(dep_times):
            dep_dates.append(dep_dates[-1])
            
        # find airports
        temp = email[i].strip('()')
        if temp in airport_codes:
            airports.append(temp)
        # find cost
        if cost == None and follows(email, i, ['total paid:', 'total paid', 'total:', 'total']) != None:
            for j in range(min(len(email)-i, 5)):
                m = re.match("\$*\d+\.\d{2}", email[i+j])
                if bool(m):
                    cost = m.group(0)
                    break
        if cost != None and cost[0] != '$':
            cost = '$' + cost

        # find name
        if i < len(email) - 2 and name == None:
            name_len = 2
            name = before(email, i, ['join the aadvantage','aadvantage'], name_len, ['passenger'])
            if name == None:
                name = follows(email, i, heuristics['name'], name_len, ['passenger info'])
            if name != None:
                if '/' in name:
                    name = name.split()[0]
                name = name.strip(',')
        # find confirmation number
        temp = follows(email, i, heuristics['confirmation'])
        if temp != None and confirmation == None:
            confirmation = temp
        # find airline
        if current_lower in airlineIATA:
            if current_lower in counter:
                counter[current_lower] += 1
            else:
                counter[current_lower] = 1

    # airline appears most is selected
    airline = max(counter.items(), key=operator.itemgetter(1))[0]

    # heuristic for calculating # flights
    num_flights = min(len(dep_times), len(arr_times))

    # packaging individual flight data
    times = []
    for i in range(num_flights):
        times.append((dep_times[i], arr_times[i]))
    dates = [(d, d) for d in dep_dates]
    airport_pairs = findLongestChain(airports)

    # timezones
    timezones = dict()
    for pair in airport_pairs:
        timezones[pair[0]] = getTimezone(airport_codes[pair[0]])
    if len(airport_pairs) > 0:
        timezones[airport_pairs[-1][1]] = getTimezone(
            airport_codes[airport_pairs[-1][1]]
        )

    # calculate durations
    for i in range(min(len(dates), len(times), len(airport_pairs))):
        dep_date, arr_date = dates[i]
        dep_time, arr_time = times[i]
        a1, a2 = airport_pairs[i]
        t1, t2 = timezones[a1], timezones[a2]
        departure, arrival = getDateTime(dep_date, dep_time), getDateTime(
            arr_date, arr_time
        )
        if dep_time[-2:] == "PM" and arr_time[-2:] == "AM":
            arrival += timedelta(days=1)  # FIXME
        delta = arrival - departure
        offset = tzDiff(dep_date, t1, t2)
        if delta.total_seconds() + offset:
            durations.append(secondsToHours(delta.total_seconds() + offset))
        else:
            durations.append(None)
            err_flag = True

    # if too many flights get rid of possible duplicates, raise warning
    if len(flights) > num_flights:
        flights = list(set(flights))
        err_flag = True

    # fix flight number if needed
    for i, flight in enumerate(flights):
        f = flight.split()
        if f[0].lower() in {"flight", "alaska"}:
            flights[i] = airlineIATA[airline] + " " + f[1]
        elif len(f) == 1:
            flights[i] = airlineIATA[airline] + " " + f[0]

    # pad missing values with None
    pad(
        [times, dates, airport_pairs, flights, durations],
        [(None, None), (None, None), (None, None), None, None],
    )

    info = {
        "name": name,
        "confirmation_num": confirmation,
        "airline": airline.capitalize(),
        "cost": cost,
        "flights": [],
    }

    for i in range(num_flights):
        info["flights"].append(
            {
                "flight": flights[i],
                "airport1": airport_pairs[i][0],
                "airport2": airport_pairs[i][1],
                "dep_date": dates[i][0],
                "arr_date": dates[i][1],
                "dep_time": times[i][0],
                "arr_time": times[i][1],
                "duration": durations[i],
            }
        )

    summary(info)

    missing = countNone(info)
    print_err = False
    err_msg = ""
    if err_flag or airline == "delta":
        err_msg += "There are potential parsign errors.\n"
        print_err = True
    if missing > threshold:
        err_msg += f"{missing} values are missing, please check output.\n"
        print_err = True

    if print_err:
        print("**** WARNING ****\n" + err_msg + "*****************")
    return info


"""
===============================
------ Helper functions -------
===============================
"""


def summary(info):
    print(
        f"Passenger: {info['name']}   Confirmation Number: {info['confirmation_num']}\n"
        f"Airline: {info['airline']}\n"
        f"========================================================\n"
    )
    for f in info["flights"]:
        print(
            f"Flight: {f['flight']} from {f['airport1']} to {f['airport2']}\n\n"
            f"Departs on {f['dep_date']} at {f['dep_time']}\nArrives on {f['arr_date']} at {f['arr_time']}\n"
            f"Flight duration: {f['duration']}\n\n"
            f"--------------------------------------------------------\n"
        )
    print(
        f"\nTotal Cost: {info['cost']}\n"
        f"========================================================\n"
    )


def preprocess(part) -> str:
    """
    Preprocesses email to be read by parser.

            Params:
                        part (dict): contains email payload
            Returns:
                        email (list[str]): list of words in processed email
    """
    soup = soupify(part)
    all_strings = soup.find_all(string=re.compile(".*"))
    [
        string.parent.clear()
        for string in all_strings
        if string != None and string.parent != None and len(string.strip()) > 100
    ]
    email = unicodetoascii(getTextString(soup))
    email = replace(email, ["-", "*", "\u2014", "\u2013"]).split()
    return email


def countNone(obj):
    """
    Recursively counts # of None values in obj
    """
    if obj == None:
        return 1
    elif type(obj) == list or type(obj) == tuple:
        return sum([countNone(o) for o in obj])
    elif type(obj) == dict:
        return sum([countNone(obj[k]) for k in obj.keys()])
    else:
        return 0


def soupify(part, parser="lxml"):
    """
    Extracts email and converts to BeautifulSoup object

            Params:
                        part (dict):  contains email payload
                        parser (str): html parser to use, default "lxml"
            Returns:
                        BeaufifulSoup object of html
    """
    html = decode(part["body"]["data"])
    return BeautifulSoup(html, parser)


def pad(lists, values=None):
    """
    Pads lists to match max length list with value

            Params:
                        lists (list[list[...]]): lists to pad
                        value (list[...]): values to pad with, default None (same len as lists)
            Returns:
                        None
    """
    N = max([len(l) for l in lists])
    if values == None:
        for l in lists:
            l += [None] * (N - len(l))
    else:
        assert len(values) == len(lists)
        for i, l in enumerate(lists):
            l += [values[i]] * (N - len(l))


def isValidTime(email, i):
    if ":" not in email[i]:
        return False
    pattern = "^([0-9]{1,2}:[0-9][0-9])([aA]|[pP]m){0,1}"
    if bool(re.match(pattern, email[i])):
        return True


def getDateTime(date_string: str, time_string: str) -> datetime:
    """
    Creates datetime from date and time strings.

            Params:
                        date_string (str):  str of format "MM/DD" or "MM/DD/YYYY"
                        time_string (str):  str of format e.g. "12:38 PM"
            Returns:
                        datetime object of combined date and time
    """
    date_parts = date_string.split("/")
    day, month, year = int(date_parts[1]), int(date_parts[0]), date.today().year
    time_parts = time_string.split()
    t = time_parts[0].split(":")
    hour, minute = int(t[0]), int(t[1])
    if hour != 12 and time_parts[1].lower() == "pm":
        hour += 12
    return datetime(year, month, day, hour, minute, 0, tzinfo=utc)


def isValidDate(email, i):
    if i < len(email) - 1 and email[i].lower()[:-1] in days:
        # 6/18/2021
        if bool(re.match("\d{1,2}/\d{2}/(\d{2}|\d{4})", email[i + 1])):
            return email[i + 1]
        # Sun, 09Aug
        day, month = splitDigChar(email[i + 1])
        if month.lower() in months and day != "" and 1 < int(day) and int(day) < 32:
            return (
                str(months[month.lower()]) + "/" + day + "/" + str(date.today().year)
            )  # FIXME
    if i > len(email) - 3:
        return None
    # Mon, July 20
    weekday, month, day = email[i].lower(), email[i + 1].lower(), email[i + 2].lower()
    if month == ",":
        weekday += ","
        month = day
        day = email[i + 3].lower()
    if weekday[:-1] in days and weekday[-1] == "," and month in months:
        if day[-1] == ",":
            day = day[:-1]
        if day.isnumeric() and 1 < int(day) and int(day) < 32:
            return (
                str(months[month]) + "/" + str(day) + "/" + str(date.today().year)
            )  # FIXME
        else:
            return None
    else:
        return None


def follows(email, i, words, after=1, unwanted=[]):
    """
    Returns item(s) in email that follow anything in 'words'

            Params:
                        words (list[str]):  words to check if follows
                        after (int):  number of items to return after found word
                        unwanted (list[str]): words not to match
            Returns:
                        str of items that follow the matched word or None
    """
    for word in unwanted:
        word_list = word.split()
        j = len(word_list)
        if i > len(email) - j - 1:
            continue
        if " ".join(email[i : i + j]).lower() == word:
            return None
    for word in words:
        word_list = word.split()
        j = len(word_list)
        if i > len(email) - j - 1:
            continue
        if " ".join(email[i : i + j]).lower() == word:
            return " ".join(email[i + j : i + j + after])
    return None


def before(email, i, words, before=1, until=[]):
    # see follows function above
    for word in words:
        word_list = word.split()
        j = len(word_list)
        if i < before:
            continue
        if " ".join(email[i-j+1:i+1]).lower() == word:
            s = 0
            for k in range(before):
                w = email[i-j-k]
                if w.lower() in until:
                    break
                s += 1
            return " ".join(email[i-j-s+1:i-j+1])
    return None


def findLongestChain(chain):
    """
    Return the longest sequence of connected pairs in chain.

    >>> findLongestChain(['OAK', 'DEN', 'OAK', 'DEN', 'DEN', 'OAK'])
    [('OAK', 'DEN'), ('DEN', 'OAK')]

    """
    if len(chain) == 0:
        return None
    grouped = []
    for i in range(0, len(chain) - 1, 2):
        grouped.append((chain[i], chain[i + 1]))
    end, prev = 0, grouped[0]
    curr_len, max_len = 0, 0
    for i, v in enumerate(grouped):
        if prev[1] == v[0]:
            curr_len += 1
        else:
            curr_len = 1
        if curr_len > max_len:
            max_len = curr_len
            end = i + 1
        prev = v
    return grouped[end - max_len : end]


def getTextString(soup):
    res = ""
    for string in soup.stripped_strings:
        res += string + " "
    return res

def createService():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)

def fetchEmailList(service, count=100):
    results = (
        service.users().messages().list(userId=_userId, labelIds=['INBOX'], maxResults=min(count, 500)).execute()
    )
    return results.get('messages', [])

def fetchEmailHtml(service, messages):
    """Returns message content from gmail API
    """
    ret = []
    for message in messages:
        msg = service.users().messages().get(userId=_userId, id=message['id']).execute()
        part = list(
            filter(lambda p: p["mimeType"] == "text/html", msg["payload"]["parts"])
        )[0]
        ret.append(part)
    
    return ret

def replace(text, characters, by=" "):
    for c in characters:
        text = text.replace(c, by)
    return text


def secondsToHours(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return str(int(hours)) + "h, " + str(int(minutes)) + "m"


def unicodetoascii(text):

    TEXT = (
        text.
        # replace('\\xe2\\x80\\x99', "'").
        # replace('\\xc3\\xa9', 'e').
        replace("\\xe2\\x80\\x90", "-")
        .replace("\\xe2\\x80\\x91", "-")
        .replace("\\xe2\\x80\\x92", "-")
        .replace("\\xe2\\x80\\x93", "-")
        .replace("\\xe2\\x80\\x94", "-")
        .replace("\\xe2\\x80\\x94", "-")
        .
        # replace('\\xe2\\x80\\x98', "'").
        # replace('\\xe2\\x80\\x9b', "'").
        # replace('\\xe2\\x80\\x9c', '"').
        # replace('\\xe2\\x80\\x9c', '"').
        # replace('\\xe2\\x80\\x9d', '"').
        # replace('\\xe2\\x80\\x9e', '"').
        # replace('\\xe2\\x80\\x9f', '"').
        replace("\\xe2\\x80\\xa6", "...")
        .
        # replace('\\xe2\\x80\\xb2', "'").
        # replace('\\xe2\\x80\\xb3', "'").
        # replace('\\xe2\\x80\\xb4', "'").
        # replace('\\xe2\\x80\\xb5', "'").
        # replace('\\xe2\\x80\\xb6', "'").
        # replace('\\xe2\\x80\\xb7', "'").
        # replace('\\xe2\\x81\\xba', "+").
        replace("\\xe2\\x81\\xbb", "-")
        # replace('\\xe2\\x81\\xbc', "=").
        # replace('\\xe2\\x81\\xbd', "(").
        # replace('\\xe2\\x81\\xbe', ")")
    )
    return TEXT


def strip(txt):
    return (
        txt.replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        .replace("    ", " ")
        .replace("  ", " ")
        .replace("  ", " ")
        .replace("   ", " ")
        .strip()
    )


def splitCharDig(txt):
    for i in range(len(txt)):
        if txt[i].isnumeric():
            return txt[:i], txt[i:]
    return None, None


def splitDigChar(txt):
    for i in range(len(txt)):
        if txt[i].isalpha():
            return txt[:i], txt[i:]
    return None, None


# utility
days = {
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sun",
    "mon",
    "tue",
    "tues",
    "wed",
    "thurs",
    "thur",
    "fri",
    "sat",
    "thu",
}
months = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
airlineIATA = {
    "delta": "DL",
    "american": "AA",
    "united": "UA",
    "southwest": "WN",
    "jetblue": "B6",
    "alaska": "AS",
}

if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print(f"Time ellapsed: {round(end - start, 4)} s")

class CodeType(enum.Enum):
    AIRPORT = "AIRPORT"
    AIRLINE = "AIRLINE"


_codes_cache = {CodeType.AIRLINE: None, CodeType.AIRPORT: None}


def _data_file(fname: str) -> str:
    """Returns abs file path for files in data directory"""
    return os.path.join(curr_file_dir, f"data/{fname}")


def get_codes(code_type: CodeType):
    cached = _codes_cache.get(code_type)
    if cached:
        return cached
    else:
        with open(
            _data_file(f"{str(code_type.value).lower()}_codes.pickle"), "rb"
        ) as pickle_file:
            codes = pickle.load(pickle_file)
            _codes_cache[code_type] = codes
            return codes
