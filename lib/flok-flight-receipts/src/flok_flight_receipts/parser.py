from __future__ import print_function

import sys
import enum
import operator
import os.path
import pickle
import re
import json
import math
import time
from base64 import urlsafe_b64decode as decode
from datetime import date, datetime, timedelta
from typing import List

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2 import service_account
from pytz import utc

from .timezone import getTimezone, tzDiff
from .sheets import SHEET_TAB_ID

# If modifying these scopes, delete the file token.pickle.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def _data_file(fname: str) -> str:
    """Returns abs file path for files in data directory"""
    return os.path.join(curr_file_dir, f"data/{fname}")


curr_file_dir = os.path.dirname(os.path.realpath(__file__))
airport_codes_to_names = pickle.load(open(_data_file("airport_codes_to_names.pickle"), "rb"))
airport_names_to_codes = pickle.load(open(_data_file("airport_names_to_codes.pickle"), "rb"))
airline_codes_to_names = pickle.load(open(_data_file("airline_codes_to_names.pickle"), "rb"))
airline_names_to_codes = pickle.load(open(_data_file("airline_names_to_codes.pickle"), 'rb'))
airport_codes_to_timezones = pickle.load(open(_data_file("airport_codes_to_timezones.pickle"), 'rb'))
heuristics = json.load(open(_data_file("heuristics.json"), "r"))

def main():
    # fetching from gmail API
    service = build_service()
    messages = fetch_email_list(service)
    parts = fetch_email_html(service, messages)

    # processing
    emails_cleaned, emails_full = [], []
    for p in parts:
        cleaned, full = preprocess(p)
        emails_cleaned.append(cleaned)
        emails_full.append(full)

    results = []
    for i in range(len(emails_cleaned)):
        print(i + 1)
        info = parse(emails_cleaned[i], emails_full[i])
        results.append(info)
        print("\n")

    return results

def parse_emails(emails, logging=False):
    """
        Params
            emails (List[{ 'id': string, 'part': email, 'err': 'string' }]): list of email objects, 'err' optional
            logging (bool): display progress bar if true
        Returns
            tuple of list of parsed results and list of errors
    """
    # processing
    errs = []
            
    results = []
    for email in progressBar(emails, prefix = 'Progress:', suffix = 'Complete', length = 50, logging=logging):
        if 'part' not in email:
            errs.append(email)
            continue
        cleaned, full = preprocess(email['part'])
        info = parse(cleaned, full)
        if info:
            results.append({**info, 'address': email['address'], 'subject': email['subject'], 'id': email['id']})
        else:
            errs.append({'id': email['id'], 'err': 'not a receipt', 'address': email['address'], 'subject': email['subject']})

    return results, errs
    
def parse(email: List[str], email_full: List[str], threshold=0, logging=False) -> None:
    """
    Prints summary of parsed email.

            Params:
                        email (list[str]):   list of all words in the email
                        airport_codes_to_names (dict[str,str]):    map from airport code to name
                        airline_codes_to_names (dict[str,str]):    map from airline code to name
            Returns:
                        None
    """
    cost, confirmation, passenger_name, airline = None, None, None, None
    
    airports, flights = [], []
    arr_dates, arr_times, dep_dates, dep_times, durations = [], [], [], [], []

    da_flag = [True]  # alternates b/w appending to dep_time or arr_time
    err_flag = False  # set if potential parsing errors
    err_msg = ""
    delay_flag, stop_flag = False, False
    overnight_flag = [False]

    use_arr_and_dep_dates, use_airport_names = set(), set()

    include_parenth = False
    airline_code, airline, err_msg = find_airline(email_full, use_arr_and_dep_dates, use_airport_names, heuristics)
    if airline != None:
        delay_flag = delay_start(email, 0, airline, use_arr_and_dep_dates, use_airport_names)
        if airline.lower() == "united airlines":
            include_parenth = True
        if airline.lower() == "easyjet":
            print("easyJet not supported yet.")
            return

    for i in range(len(email)):
        current = email[i].lower()
        if current == '':
            continue
        stop_flag = stop(email, i, airline)
        if delay_flag:
            delay_flag = delay_start(email, i, airline, use_arr_and_dep_dates, use_airport_names)
        elif not stop_flag:
            find_flights(email, i, flights, current)
            find_times(email, i, dep_times, arr_times, overnight_flag, da_flag, current)
            find_dates(email, i, dep_dates, arr_dates, dep_times, arr_times, overnight_flag, airline, use_arr_and_dep_dates)
            find_airports(email, i, airports, use_airport_names, airline, include_parenth=include_parenth)
            find_durations(email, i, durations)

        if cost == None:
            cost = find_cost(email, i, airline)

        if passenger_name == None:
            passenger_name = find_name(email, i, airline)

        # find confirmation number
        temp = follows(email, i, heuristics['confirmation'])
        if temp != None and confirmation == None and temp.isalnum():
            confirmation = temp

    # heuristic for calculating # flights
    num_flights = len(arr_times)

    if num_flights == 0 or (not airline and len(flights) == 0):
        return

    # fix flight number if needed
    if airline_code:
        for i, flight in enumerate(flights):
            f = flight.split()
            if f[0].lower() in {"flight"}:
                flights[i] = airline_code.upper() + " " + f[1]
            elif len(f) == 1:
                flights[i] = airline_code.upper() + " " + f[0]

    # packaging individual flight data
    times = []
    for i in range(num_flights):
        times.append((dep_times[i], arr_times[i]))

    pad([dep_dates, arr_dates], longest_len=num_flights)
    dates = [[dep_dates[i], arr_dates[i]] for i in range(num_flights)]

    pad([airports], longest_len=2 * num_flights)
    airport_pairs = []
    for i in range(0, 2 * num_flights, 2):
        if i+1 < len(airports):
            airport_pairs.append((airports[i], airports[i+1]))
        else:
            airport_pairs.append((airports[i], None))

    # calculate durations if not found
    if len(durations) != num_flights and airport_pairs != None:
        timezones = dict()
        for a1, a2 in airport_pairs:
            if a1 and a1 not in timezones:
                if a1 in airport_codes_to_timezones:
                    timezones[a1] = airport_codes_to_timezones[a1]
                elif airline in use_airport_names:
                    try:
                        timezones[a1] = getTimezone(a1)
                    except:
                        pass
            if a2 and a2 not in timezones:
                if a2 in airport_codes_to_timezones:
                    timezones[a2] = airport_codes_to_timezones[a2]
                elif airline in use_airport_names:
                    try:
                        timezones[a2] = getTimezone(a2)
                    except:
                        pass

        for i in range(min(len(dates), len(times), len(airport_pairs))):
            dep_date, arr_date = dates[i]
            dep_time, arr_time = times[i]
            a1, a2 = airport_pairs[i]
            if not a1 or a1 not in timezones or not a2 or a2 not in timezones or not dep_date or not arr_date:
                durations.append(None)
                err_flag = True
                continue
            t1, t2 = timezones[a1], timezones[a2]
            departure, arrival = get_datetime(dep_date, dep_time), get_datetime(
                arr_date, arr_time
            )

            delta = arrival - departure
            offset = tzDiff(dep_date, t1, t2)
            if delta.total_seconds() + offset > 0:
                durations.append(seconds_to_hours(delta.total_seconds() + offset))
            else:
                durations.append(None)
                err_flag = True

    # pad missing values with None
    pad(
        [times, dates, airport_pairs, flights, durations],
        [(None, None), (None, None), (None, None), None, None],
    )
    
    info = {
        "name": passenger_name,
        "confirmation_num": confirmation,
        "airline": airline,
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

    missing = countNone(info)
    if err_flag:
        err_msg += "There are potential parsign errors.\n"
    if missing > threshold:
        err_msg += f"{missing} values are missing, please check output.\n"
        err_flag = True

    if logging:
        print("**** WARNING ****\n" + err_msg + "*****************")
    
    if err_flag:
        info["error"] = err_msg
    else:
        info["error"] = None

    return info


"""
===============================
------ Helper functions -------
===============================
"""

def check_heuristic(email, i, airline, field):
    """
        Checks for heuristic match following or before current item.
        Returns match if found, else returns False
    """
    if airline in heuristics and field in heuristics[airline]:
        field_heuristics = heuristics[airline][field]
        if 'follows' in field_heuristics:
            return follows(email, i, **field_heuristics['follows'])
        if 'before' in field_heuristics:
            return before(email, i, **field_heuristics['before'])
    else:
        if 'default' in heuristics and field in heuristics['default']:
            default_heuristics = heuristics['default'][field]
            if 'follows' in default_heuristics:
                return follows(email, i, **default_heuristics['follows'])
            if 'before' in default_heuristics:
                return before(email, i, **default_heuristics['before'])
        else:
            return False
    
    return False


def delay_start(email, i, airline, use_arr_and_dep_dates, use_airport_names):
    # edge case
    if airline == "united airlines":
        if follows(email, i, ['trip summary']):
            return False
        elif follows(email, i, ['flight 1 of']):
            use_arr_and_dep_dates.add(airline)
            return False
        return True

    start = check_heuristic(email, i, airline, 'start')

    # edge case for delta forwarded itinerary
    if start and airline == "delta airlines":
        if airline in use_airport_names and follows(email, i, ['your forwarded itinerary']):
            use_airport_names.remove(airline)

    if start or start == False:
        return False
    else:
        return True

def stop(email, i, airline):
    return bool(check_heuristic(email, i, airline, 'stop'))

def find_flights(email, i, flights, current):
    if i + 2 < len(email):
        flight = follows(email, i, ['flight #'])
        if flight != None:
            flights.append(flight)
        elif (current in airline_codes_to_names or current in {'flight'}):
            if i < len(email) - 3 and bool(re.match("\d+ of \d+", " ".join(email[i+1:i+4]))):
                pass
            elif bool(re.match("^([0-9]{1,4})$", email[i+1])):
                flights.append(email[i] + " " + email[i+1])
        elif before(email, i, ['flight number:']):
            if email[i+1].lower() in airline_codes_to_names and i < len(email) - 2:
                if bool(re.match("^([0-9]{1,4})$", email[i+2])):
                    flights.append(email[i+1] + " " + email[i+2])
        else:
            chars, nums = None, None
            if current[:6].lower() == 'flight':
                chars, nums = split_char_dig(current[6:])
            else:
                chars, nums = split_char_dig(email[i])
            if chars != None and chars.lower() in airline_codes_to_names and bool(re.match("^([0-9]{1,4})$", nums)):
                flights.append(chars.upper() + " " + nums)
    if len(flights) > 1:
        if flights[-1] == flights[-2]:
            flights.pop()

def find_times(email, i, dep_times, arr_times, overnight_flag, da_flag, current):
    if is_valid_time(email, i):
        time = current
        hour, minute = "", ""
        if i < len(email) - 1 and email[i+1][:2].lower() in ['am', 'pm']:
            time = email[i] + " " + email[i+1][:2].lower()
        if 'am' in time:
            hour, minute = time[:time.find('am')].strip().split(':')
            if hour == '12':
                hour = '00'
        elif 'pm' in time:
            hour, minute = time[:time.find('pm')].strip().split(':')
            if hour != '12':
                hour = str(int(hour) + 12)
        elif 'h' in time:
            hour, minute = email[i].split('h')
        else:
            hour, minute = email[i].split(':')

        if len(dep_times) > len(arr_times):
            if int(dep_times[-1].split(':')[0]) >= 12 and int(hour) < 12:
                overnight_flag[0] = True

        if da_flag[0]:
            dep_times.append(hour + ":" + minute)
        else:
            arr_times.append(hour + ":" + minute)

        da_flag[0] = not da_flag[0]     # alternate b/w dep and arr times

def find_dates(email, i, dep_dates, arr_dates, dep_times, arr_times, overnight_flag, airline, use_arr_and_dep_dates):    
    if overnight_flag[0] and len(arr_dates) == len(arr_times) and airline not in use_arr_and_dep_dates:
        arr_dates[-1] = (get_datetime(arr_dates[-1]) + timedelta(days=1)).strftime("%-m/%-d/%Y")
        overnight_flag[0] = False
    
    date = is_valid_date(email, i, airline)
    if date != None:
        if airline in use_arr_and_dep_dates:
            if len(dep_dates) > len(arr_dates):
                arr_dates.append(date)
            else:
                dep_dates.append(date)
        else:
            dep_dates.append(date)
            arr_dates.append(date)
    # assigns dateless flights to most recent date
    elif len(dep_dates) != 0 and len(dep_dates) < len(dep_times):
        dep_dates.append(arr_dates[-1])
        arr_dates.append(arr_dates[-1])

def find_airports(email, i, airports, airport_names, airline=None, include_parenth=False):
    current = email[i].strip()
    if include_parenth and (current[0] != '(' or current[-1] != ')'):
        return
    curr = current.strip('()')
    if airline and airline in airport_names:
        if i < len(email) - 6:
            for j in range(6):
                name = replace(" ".join(email[i:i+j+1]),['(',')',','], '')
                if name.lower() in airport_names_to_codes:
                    airports.append(name)
                    break
    elif curr in airport_codes_to_names:
        airports.append(curr)

def find_cost(email, i, airline):
    cost = check_heuristic(email, i, airline, 'cost')
            
    if cost:
        valid = False
        for curr in cost.split():
            curr = curr.replace(",","")
            m = re.match("^\$?\d+(\.\d{2})?$", curr)
            if bool(m):
                valid = True
                cost = m.group(0)
                break
        if not valid:
            cost = None
    else:
        cost = None
        
    if cost != None and cost[0] != '$':
        cost = '$' + cost
    return cost

def find_name(email, i, airline):
    name = check_heuristic(email, i, airline, 'name')

    # cleanup name
    if name:
        if '/' in name:
            name = " ".join(name.split()[0].split('/')[::-1])
        comma = name.find(',')
        if comma != -1:
            name = name[:name.find(',')]
        if name.split()[0].lower() in { 'mr', 'ms', 'mrs', 'mr.', 'ms.', 'mrs.','miss','miss.'}:
            name = " ".join(name.split()[1:])
        if not (name.isalpha() or " " in name or "'" in name):
            name = None
        return name
    else:
        return None

def find_durations(email, i, durations):
    if before(email, i, ['duration','duration:','est. travel time']) and i < len(email) - 4:
        # 1h 55m
        if bool(re.match("\d{0,2}h \d{0,2}m", email[i+1] + " " + email[i+2])):
            durations.append(email[i+1] + " " + email[i+2])
        # edge case 1h ours39minutes
        elif bool(re.match("\d{0,2}h ours \d{0,2}m", email[i+1] + " " + email[i+2] + " " + email[i+3])):
            durations.append(email[i+1] + " " + email[i+3])
        # 55m or 8h
        elif bool(re.match("\d{0,2}(m|h)", email[i+1])):
            durations.append(email[i+1])
        # 1 hr 4 min
        elif bool(re.match("\d{0,2} hr \d{0,2} min", " ".join(email[i+1:i+5]))):
            durations.append(" ".join(email[i+1:i+5]))

def find_airline(email, use_arr_and_dep_dates, use_airport_names, heuristics):
    counter = dict()
    airline_code, airline, err_msg = None, None, ""
    flights = []
    contains_google = False # edge case for alaksa google flights receipt

    for i in range(len(email)):
        current = email[i].lower()
        if current == "google":
            contains_google = True
        # find flights
        if len(flights) < 1:
            find_flights(email, i, flights, current)
        # find airline
        if current in airline_names_to_codes or (i < len(email) - 1 and " ".join(email[i:i+2]) in airline_names_to_codes):
            airline_code = airline_names_to_codes[current]
            if airline_code in counter:
                counter[airline_code] += 1
            else:
                counter[airline_code] = 1

    # airline appears most is selected
    if counter:
        airline_code = max(counter.items(), key=operator.itemgetter(1))[0]
        airline = airline_codes_to_names[airline_code].lower()
        if len(counter.keys()) > 1 and counter[airline_code] < 3:
            airline_code, airline, err_msg = None, None, "Airline not found.\n"
    else:
        err_msg = "Airline not found.\n"
    
    # if no airline found default to first flight carrier
    if not airline and flights:
        airline_code = flights[0].split()[0].lower()
        airline = airline_codes_to_names[airline_code].lower()
        err_msg = ""

    if airline in heuristics and 'arr_and_dep_dates' in heuristics[airline]:
        if airline == "alaska airlines" and contains_google:
            pass
        else:
            use_arr_and_dep_dates.add(airline)
    if airline in heuristics and 'airport_names' in heuristics[airline]:
        use_airport_names.add(airline)

    return airline_code, airline, err_msg

def progressBar(iterable, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r", logging=False):
    """
    Call in a loop to create terminal progress bar
    @params:
        iterable    - Required  : iterable object (Iterable)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    total = len(iterable)
    # Progress Bar Printing Function
    def printProgressBar (iteration):
        percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print(f'\r{prefix} |{bar}| {percent}% {suffix}', end = printEnd)
    # Initial Call
    if logging:
        printProgressBar(0)
        # Update Progress Bar
        for i, item in enumerate(iterable):
            yield item
            printProgressBar(i + 1)
        # Print New Line on Complete
        print()
    else:
        for item in iterable:
            yield item


def capitalize(string):
    if string:
        return " ".join([s.capitalize() for s in string.split()])

def preprocess(part) -> str:
    """
    Preprocesses email to be read by parser.
            Params:
                        part (dict): contains email payload
            Returns:
                        email (list[str]): list of words in processed email
    """
    pickle.dump(part, open("test.pickle", 'wb'))
    soup = soupify(part)
    stripped = []
    # get rid of whitespace and extraneous characters
    for s in soup.stripped_strings:
        while "  " in s:
            s = s.replace("  ", " ")
        s = s.replace("\xa0", " ").replace("\r\n", "").replace("Â","").replace("\u200c", "")
        stripped.append(s)
    # remove email forward header
    words = remove_header(stripped)
    # remove long strings
    words = [ w for w in words if len(w) < 55 or ':' in w or w[:3] in airport_codes_to_names ]
    words = unicode_to_ascii(" ".join(words))
    # edge case
    words = words.replace('Face masks required for all travelers','')
    words = words.replace('\u2019', "'")
    words = replace(words, ["-", "*", "\u2014", "\u2013"]).split()

    raw = " ".join(stripped).split()

    # edge case
    index = None
    for i in range(len(words)):
        if words[i][-4:] == "Join":
            index = i
    if index != None:
        words[index] = words[index][:-4]
        words.insert(index + 1, "Join")

    return words, raw

def remove_header(text: List[str]):
    words = []
    skip = -1
    keywords = ['From:', 'Subject:', 'Date:', 'To:', 'Reply-To:']
    for i, string in enumerate(text):
        for w in keywords:
            if i < 100 and string[:len(w)] == w:
                if i < len(text) + 1 and text[i+1][-1] and text[i+1][-1] == '<':
                    skip = 3
                elif i < len(text) + 2 and text[i+2][0] == '<':
                    skip = 2
                elif w == 'Date:':
                    flag = False
                    for j in range(i+1, min(i+5,len(text))):
                        if bool(re.match("\d{1,2}:\d{1,2}",text[j])):
                            skip = j - i
                            flag = True
                            break
                    if not flag:
                        skip = 1
                else:
                    skip = 1
                break
        if skip < 0:
            words.append(string)
        else:
            skip = skip - 1
    return words

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


def pad(lists, values=None, longest_len=0):
    """
    Pads lists to match max length list with value

            Params:
                        lists (list[list[...]]): lists to pad
                        value (list[...]): values to pad with, default None (same len as lists)
                        longest_len (int): length to pad to
            Returns:
                        None
    """
    longest_len = max(max([len(l) for l in lists]), longest_len)
    if values == None:
        for l in lists:
            l += [None] * (longest_len - len(l))
    else:
        assert len(values) == len(lists)
        for i, l in enumerate(lists):
            l += [values[i]] * (longest_len - len(l))


def is_valid_time(email, i):
    # 10:30 am
    if bool(re.match("^([0-9]{1,2}:[0-9][0-9]) {0,1}(([aA]|[pP])[mM])$", email[i])):
        return True
    # 10:30
    elif bool(re.match("^([0-9]{1,2}:[0-9][0-9])$", email[i])):
        return True
    # 14h34
    elif bool(re.match("^(\d{1,2}h\d{1,2})$", email[i])):
        if before(email, i-1, ['check in deadline :']) == None:
            return True
    return False


def get_datetime(date_string: str, time_string: str = "00:00 AM") -> datetime:
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

    if len(time_parts) != 1 and hour != 12 and time_parts[1].lower() == "pm":
        hour += 12
    return datetime(year, month, day, hour, minute, 0, tzinfo=utc)


def is_valid_date(email, i, airline):
    if airline == "royal dutch airlines":
        if i < len(email) - 4:
            weekday, day, month, year = email[i].lower(), email[i + 1].lower(), email[i + 2].lower(), email[i + 3].lower()
            if weekday in days and is_day(day) and month in months and bool(re.match("^\d{2}(\d{2})?$", year)):
                return str(months[month]) + "/" + day + "/" + year
        return
    # 6/18/2021
    if bool(re.match("\d{1,2}/\d{1,2}/(\d{2}|\d{4})", email[i])):
        month, day, year = email[i].split('/')
        if int(month) > 12 and int(day) <= 12:
            return day + "/" + month + "/" + year
        return email[i]
    if i < len(email) - 1 and email[i].lower()[:-1] in days:
        # Sun, 09Aug
        day, month = split_dig_char(email[i + 1])
        if month.lower() in months and day != "" and 1 < int(day) and int(day) < 32:
            return (
                str(months[month.lower()]) + "/" + day + "/" + str(date.today().year)
            )  # FIXME
    if i > len(email) - 4:
        return None
    # edge case
    if airline == "united airlines" and bool(re.match("(depart)|(arrive) [a-z]+:", " ".join(email[i-2:i]).lower())):
        return None
    _0, _1, _2, _3 = email[i].lower(), email[i + 1].lower(), email[i + 2].lower(), email[i + 3].lower()
    # 11 Jul 2021 or 21
    day, month, year = _0, _1, _2
    if is_day(day) and month in months and bool(re.match("^\d{2}(\d{2})?$", year)):
        return str(months[month]) + "/" + day + "/" + year.strip(",").strip(":").strip()
    # Mon, 12 July 2021 or 21
    weekday, day, month, year = _0, _1, _2, _3.strip(",").strip(":").strip()
    if (weekday[-1] == "," or weekday[-1] == ".") and weekday[:-1] in days and is_day(day) and month in months and bool(re.match("^\d{2}(\d{2})?$", year)):
        return str(months[month]) + "/" + day + "/" + year
    # Mon, July 20
    weekday, month, day = _0, _1, _2
    if month == ",":
        weekday += ","
        month = day
        day = email[i + 3].lower()
    if weekday[:-1] in days and weekday[-1] == "," and month in months:
        if day[-1] == ",":
            day = day[:-1]
        if is_day(day):
            return (
                str(months[month]) + "/" + str(day) + "/" + str(date.today().year)
            )  # FIXME
        else:
            return None
    else:
        return None

def is_day(day):
    return day.isnumeric() and 1 < int(day) and int(day) < 32

def follows(email, i, words=[], after=1, unwanted=[]):
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


def before(email, i, words=[], before=1, until=[]):
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


def find_longest_chain(chain):
    """
    Return the longest sequence of connected pairs in chain.

    >>> find_longest_chain(['OAK', 'DEN', 'OAK', 'DEN', 'DEN', 'OAK'])
    [('OAK', 'DEN'), ('DEN', 'OAK')]

    """
    if len(chain) <= 1:
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

def build_gmail_service(service_acc_info, userId):
    creds = service_account.Credentials.from_service_account_info(service_acc_info, scopes=SCOPES).with_subject(userId)
    return build('gmail','v1',credentials=creds)

def build_service(creds=None):
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

def fetch_email_list(service, _userId, count=100, to='flights@goflok.com'):
    messages = []
    req = service.users().messages().list(userId=_userId, maxResults=500, q=f'to:{to}')
    res = req.execute()

    while len(messages) < count:
        prev_req = req
        if 'messages' in res:
            messages += res['messages']
        req = service.users().messages().list_next(prev_req, res)
        if req != None:
            res = req.execute()
        else:
            break

    return messages

def fetch_email_html(service, messages, _userId):
    """Returns message content from gmail API
    """
    ret = []
    batch_size = 100

    def create_callback(id=""):
        def callback(request_id, response, exception):
            if exception is not None:
                ret.append({'id': id, 'err': exception})
            else:
                if "payload" in response:
                    from_address = ''
                    subject_line = ''
                    for header in response["payload"]["headers"]:
                        if header["name"] == "From":
                            from_address = header["value"].split('\u003c')[-1][:-1]
                        elif header["name"] == "Subject":
                            subject_line = header["value"]
                        if from_address and subject_line:
                            break
                    if "parts" in response["payload"]:
                        part = list(
                            filter(lambda p: p["mimeType"] == "text/html", response["payload"]["parts"])
                        ) 
                        if part:
                            ret.append({'id': id,'part': part[0], 'address': from_address, 'subject': subject_line})
                        else:
                            alternative_part = list(
                                filter(lambda p: p["mimeType"] == "multipart/alternative", response["payload"]["parts"])
                            )
                            if alternative_part:
                                part_from_alt = list(
                                    filter(lambda p: p["mimeType"] == "text/html", alternative_part[0]["parts"])
                                )
                                if part_from_alt:
                                    ret.append({'id': id,'part': part_from_alt[0], 'address': from_address, 'subject': subject_line})
                                else:
                                    ret.append({'id': id, 'err': 'no part in alt part', 'address': from_address, 'subject': subject_line})
                            else:
                                ret.append({'id': id, 'err': 'no part/alt part', 'address': from_address, 'subject': subject_line})
                    else:
                        ret.append({'id': id, 'err': 'no parts in payload', 'address': from_address, 'subject': subject_line})
                else:
                    ret.append({'id': id, 'err': 'no payload', 'address': '', 'subject': ''})
        return callback

    for i in range(math.ceil(len(messages) / batch_size)):
        batch = service.new_batch_http_request()
        for message in messages[i*batch_size:(i+1)*batch_size]:
            request = service.users().messages().get(userId=_userId, id=message['id'])
            batch.add(request=request, callback=create_callback(message['id']))
        batch.execute()
    
    return ret

def replace(text, characters, by=" "):
    for c in characters:
        text = text.replace(c, by)
    return text


def seconds_to_hours(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return str(int(hours)) + "h, " + str(int(minutes)) + "m"


def unicode_to_ascii(text: str) -> str:

    TEXT = (
        text
        .replace('\\xe2\\x80\\x99', "'")
        .replace('\\xc3\\xa9', 'e')
        .replace("\\xe2\\x80\\x90", "-")
        .replace("\\xe2\\x80\\x91", "-")
        .replace("\\xe2\\x80\\x92", "-")
        .replace("\\xe2\\x80\\x93", "-")
        .replace("\\xe2\\x80\\x94", "-")
        .replace("\\xe2\\x80\\x94", "-")
        .replace('\\xe2\\x80\\x98', "'")
        .replace('\\xe2\\x80\\x9b', "'")
        .replace('\\xe2\\x80\\x9c', '"')
        .replace('\\xe2\\x80\\x9c', '"')
        .replace('\\xe2\\x80\\x9d', '"')
        .replace('\\xe2\\x80\\x9e', '"')
        .replace('\\xe2\\x80\\x9f', '"')
        .replace("\\xe2\\x80\\xa6", "...")
        .replace('\\xe2\\x80\\xb2', "'")
        .replace('\\xe2\\x80\\xb3', "'")
        .replace('\\xe2\\x80\\xb4', "'")
        .replace('\\xe2\\x80\\xb5', "'")
        .replace('\\xe2\\x80\\xb6', "'")
        .replace('\\xe2\\x80\\xb7', "'")
        .replace('\\xe2\\x81\\xba', "+")
        .replace("\\xe2\\x81\\xbb", "-")
        .replace('\\xe2\\x81\\xbc', "=")
        .replace('\\xe2\\x81\\xbd', "(")
        .replace('\\xe2\\x81\\xbe', ")")
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


def split_char_dig(txt):
    for i in range(len(txt)):
        if txt[i].isnumeric():
            return txt[:i], txt[i:]
    return '', ''


def split_dig_char(txt):
    for i in range(len(txt)):
        if txt[i].isalpha():
            return txt[:i], txt[i:]
    return '', ''

def printf(*objs):
    print("\n", " ".join([o.__repr__() for o in objs]), "\n")


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

if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print(f"Time ellapsed: {round(end - start, 4)} s")

class CodeType(enum.Enum):
    AIRPORT = "AIRPORT"
    AIRLINE = "AIRLINE"


_codes_cache = {CodeType.AIRLINE: None, CodeType.AIRPORT: None}


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
