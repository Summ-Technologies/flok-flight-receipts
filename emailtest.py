from __future__ import print_function
import pickle
import re
import operator
import os.path
import time
from datetime import datetime, date, timedelta
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from base64 import urlsafe_b64decode as decode
from bs4 import BeautifulSoup
from timezone import getTimezone, tzDiff
from pytz import utc

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# user
_userId = 'testflok0@gmail.com'

def main():
    airport_codes = pickle.load(open("data/airport_codes.pickle", 'rb'))
    airline_codes = pickle.load(open("data/airline_codes.pickle", 'rb'))
    # parts = fetchEmailHtml(15)
    # pickle.dump(parts, open("data/parts.pickle", 'wb'))
    parts = pickle.load(open("data/parts.pickle", 'rb'))
    emails = [preprocess(p) for p in parts]

    for i, email in enumerate(emails):
        print(i+1)
        parse(email, airport_codes, airline_codes)
        print('\n')

def parse(email, airport_codes, airline_codes) -> None:
    '''
    Prints summary of parsed email. Assumes there are 2 flights (FIX THIS)
    The if ... == None structure is a temporary hack.

            Params:
                        email (list[str]):   list of all words in the email
                        aiport_codes (dict[str,str]):    map from airport code to name
                        airline_codes (dict[str,str]):    map from airline code to name
            Returns:
                        None
    '''
    cost, confirmation, duration1, duration2, = None, None, None, None
    airport1, airport2, flight_1, flight_2, name = None, None, None, None, None
    arr1_date, arr2_date, dep1_date, dep2_date = None, None, None, None
    arr1_time, arr2_time, dep1_time, dep2_time = None, None, None, None
    counter = dict()

    for i in range(len(email)):
        email_lower = email[i].lower()
        # find flights
        if i + 1 < len(email):
            if flight_1 == None:
                flight_1 = follows(email, i, ['flight #'])
            elif flight_2 == None:
                flight_2 = follows(email, i, ['flight #'])
            if (email_lower in airline_codes or email_lower in {'flight'}) \
                and bool(re.match("^([1-9][0-9]{1,3})$", email[i+1])):
                if flight_1 == None:
                    flight_1 = email[i] + " " + email[i+1]
                elif flight_2 == None:
                    flight_2 = email[i] + " " + email[i+1]
            chars, nums = splitCharDig(email[i])
            if chars != None and chars.lower() in airline_codes and bool(re.match("^([1-9][0-9]{1,3})$", nums)):
                if flight_1 == None:
                    flight_1 = chars + " " + nums
                elif flight_2 == None:
                    flight_2 = chars + " " + nums
            
        # find dates
        temp = isValidDate(email, i)
        if temp != None:
            if dep1_date == None:
                dep1_date = temp
            elif dep2_date == None:
                dep2_date = temp
        # find times
        if isValidTime(email, i):
            time = email_lower
            if 'am' in time:
                time = time[:time.find('am')] + " AM" 
            elif 'pm' in time:
                time = time[:time.find('pm')] + " PM"
            elif i < len(email) - 1 and email[i+1].lower() in ['am', 'pm']:
                time = email[i] + " " + email[i+1]
            
            if dep1_time == None:
                dep1_time = time
            elif arr1_time == None:
                arr1_time = time
            elif dep2_time == None:
                dep2_time = time
            elif arr2_time == None:
                arr2_time = time
        # find airports
        temp = email[i].strip('()')
        if temp in airport_codes:
            if airport1 == None:
                airport1 = temp
            elif airport2 == None:
                airport2 = temp
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
            name = before(email, i, ['join the aadvantage','aadvantage'], name_len)
            if name == None:
                name = follows(email, i, ['hi','name:','traveler details','travelers','passenger','passenger:',], name_len, ['passenger info'])
            if name != None:
                if '/' in name:
                    name = name.split()[0]
                name = name.strip(',')
        # find confirmation number
        temp = follows(email, i, ['record locator:','confirmation code is', 'confirmation code', 'confirmation code:', 'confirmation number:', 'confirmation #:', 'confirmation #'])
        if temp != None:
            confirmation = temp
        # find airline
        if email_lower in airlineIATA:
            if email_lower in counter:
                counter[email_lower] += 1
            else:
                counter[email_lower] = 1
    
    # airline appears most is selected
    airline = max(counter.items(), key=operator.itemgetter(1))[0]
    
    # timezones
    if airport1 != None and airport2 != None:
        t1, t2 = getTimezone(airport_codes[airport1]), getTimezone(airport_codes[airport2])

    # get durations from date
    arr1_date, arr2_date = dep1_date, dep2_date # FIXME
    if dep1_date != None and arr1_date != None and dep1_time != None and arr1_time != None:
        delta1 = getDateTime(dep1_date,arr1_time)-getDateTime(dep1_date,dep1_time)
        offset = tzDiff(dep1_date, t1, t2)
        duration1 = secondsToHours(delta1.total_seconds() - offset)

    if dep2_date != None and arr2_date != None and dep2_time != None and arr2_time != None:
        delta2 = getDateTime(dep2_date,arr2_time)-getDateTime(dep2_date,dep2_time)
        offset = tzDiff(dep2_date, t1, t2)
        duration2 = secondsToHours(delta2.total_seconds() + offset)

    # fix flight number if needed
    temp = flight_1.split()
    if temp[0].lower() in {"flight", "alaska"}:
        flight_1 = airlineIATA[airline] + " " + temp[1]
        flight_2 = airlineIATA[airline] + " " + temp[1]
    if len(temp) == 1:
        flight_1 = airlineIATA[airline] + " " + temp[0]
        flight_2 = airlineIATA[airline] + " " + temp[0]

    # summary
    print(
        f"Passenger: {name}   Confirmation Number: {confirmation}\n"
        f"Airline: {airline.capitalize()}\n"
        f"========================================================\n"
        f"Flight: {flight_1} from {airport1} to {airport2}\n\n"
        f"Departs on {dep1_date} at {dep1_time}\nArrives at {arr1_time}\n"
        f"Flight duration: {duration1}\n\n"
        f"--------------------------------------------------------\n"
        f"Flight: {flight_2} from {airport2} to {airport1}\n\n"
        f"Departs on {dep2_date} at {dep2_time}\nArrives at {arr2_time}\n\n"
        f"Flight duration: {duration2}\n\n\n"
        f"Total Cost: {cost}\n"
        f"========================================================\n"
    )

'''
===============================
------ Helper functions -------
===============================
'''

def preprocess(part) -> str:
    '''
    Preprocesses email to be read by parser.
    
            Params:
                        part (dict): contains email payload
            Returns:
                        email (list[str]): list of words in processed email
    '''
    soup = soupify(part)
    all_strings = soup.find_all(string=re.compile(".*"))
    [string.parent.clear() for string in all_strings 
        if string != None and string.parent != None and len(string.strip()) > 100]
    email = unicodetoascii(getTextString(soup))
    email = replace(email, ['-', '*', '\u2014', '\u2013']).split()
    return email

def soupify(part, parser="lxml"):
    '''
    Extracts email and converts to BeautifulSoup object

            Params:
                        part (dict):  contains email payload
                        parser (str): html parser to use, default "lxml"
            Returns:
                        BeaufifulSoup object of html
    '''
    html = decode(part["body"]["data"])
    return BeautifulSoup(html, parser)

def isValidTime(email, i):
    if ':' not in email[i]:
        return False
    pattern = '^([0-9]{1,2}:[0-9][0-9])([aA]|[pP]m){0,1}'
    if bool(re.match(pattern, email[i])):
        return True

def getDateTime(date_string: str, time_string: str) -> datetime:
    '''
    Creates datetime from date and time strings.

            Params:
                        date_string (str):  str of format "MM/DD" or "MM/DD/YYYY"
                        time_string (str):  str of format e.g. "12:38 PM"
            Returns:
                        datetime object of combined date and time
    '''
    date_parts = date_string.split("/")
    day, month, year = int(date_parts[1]), int(date_parts[0]), date.today().year
    time_parts = time_string.split()
    t = time_parts[0].split(':')
    hour, minute = int(t[0]), int(t[1])
    if hour != 12 and time_parts[1].lower() == 'pm':
        hour += 12
    return datetime(year, month, day, hour, minute, 0, tzinfo=utc)

def isValidDate(email, i):
    if i < len(email) - 1 and email[i].lower()[:-1] in days:
        if bool(re.match("\d{1,2}/\d{2}/(\d{2}|\d{4})",email[i+1])):
            return email[i+1]
    if i > len(email) - 3:
        return None
    weekday, month, day = email[i].lower(), email[i+1].lower(), email[i+2].lower()
    if month == ',':
        weekday += ","
        month = day
        day = email[i+3].lower()
    if weekday[:-1] in days and weekday[-1] == ',' and month in months:
        if day[-1] == ',':
            day = day[:-1]
        if day.isnumeric() and int(day) > 0 and int(day) < 32:
            return str(months[month])+"/"+str(day)+"/"+str(date.today().year) # FIXME
        else:
            return None
    else:
        return None

def follows(email, i, words, after=1, unwanted=[]):
    '''
    Returns item(s) in email that follow anything in 'words'

            Params:
                        words (list[str]):  words to check if follows
                        after (int):  number of items to return after found word
                        unwanted (list[str]): words not to match
            Returns:
                        str of items that follow the matched word or None
    '''
    for word in unwanted:
        word_list = word.split()
        j = len(word_list)
        if i > len(email) - j - 1:
            continue
        if " ".join(email[i:i+j]).lower() == word:
            return None
    for word in words:
        word_list = word.split()
        j = len(word_list)
        if i > len(email) - j - 1:
            continue
        if " ".join(email[i:i+j]).lower() == word:
            return " ".join(email[i+j:i+j+after])
    return None

def before(email, i, words, before=1):
    # see follows function above
    for word in words:
        word_list = word.split()
        j = len(word_list)
        if i < before:
            continue
        if " ".join(email[i-j:i]).lower() == word:
            return " ".join(email[i-j-before:i-j])
    return None               

def getTextString(soup):
    res = ""
    for string in soup.stripped_strings:
        res += string + " "
    return res
    
def fetchEmailHtml(count):
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
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

    service = build('gmail', 'v1', credentials=creds)

    # Get Messages
    results = service.users().messages().list(userId=_userId, labelIds=['INBOX']).execute()
    messages = results.get('messages', [])

    ret = []

    for message in messages[:count]:
        msg = service.users().messages().get(userId=_userId, id=message['id']).execute()
        part = list(filter(lambda p: p["mimeType"] == "text/html", msg["payload"]["parts"]))[0]
        ret.append(part)
    
    return ret

def replace(text, characters, by=' '):
    for c in characters:
        text = text.replace(c, by)
    return text

def secondsToHours(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return str(int(hours)) + " hr, " + str(int(minutes)) + " min"

def unicodetoascii(text):

    TEXT = (text.
    		# replace('\\xe2\\x80\\x99', "'").
            # replace('\\xc3\\xa9', 'e').
            replace('\\xe2\\x80\\x90', '-').
            replace('\\xe2\\x80\\x91', '-').
            replace('\\xe2\\x80\\x92', '-').
            replace('\\xe2\\x80\\x93', '-').
            replace('\\xe2\\x80\\x94', '-').
            replace('\\xe2\\x80\\x94', '-').
            # replace('\\xe2\\x80\\x98', "'").
            # replace('\\xe2\\x80\\x9b', "'").
            # replace('\\xe2\\x80\\x9c', '"').
            # replace('\\xe2\\x80\\x9c', '"').
            # replace('\\xe2\\x80\\x9d', '"').
            # replace('\\xe2\\x80\\x9e', '"').
            # replace('\\xe2\\x80\\x9f', '"').
            replace('\\xe2\\x80\\xa6', '...').
            # replace('\\xe2\\x80\\xb2', "'").
            # replace('\\xe2\\x80\\xb3', "'").
            # replace('\\xe2\\x80\\xb4', "'").
            # replace('\\xe2\\x80\\xb5', "'").
            # replace('\\xe2\\x80\\xb6', "'").
            # replace('\\xe2\\x80\\xb7', "'").
            # replace('\\xe2\\x81\\xba', "+").
            replace('\\xe2\\x81\\xbb', "-")
            # replace('\\xe2\\x81\\xbc', "=").
            # replace('\\xe2\\x81\\xbd', "(").
            # replace('\\xe2\\x81\\xbe', ")")
            )
    return TEXT

def strip(txt):
	return txt.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').replace('    ', ' ').replace('  ', ' ').replace('  ', ' ').replace('   ', ' ').strip()

def splitCharDig(txt):
    for i in range(len(txt)):
        if txt[i].isnumeric():
            return txt[:i], txt[i:]
    return None, None

# utility
days = { 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday',
        'sun', 'mon', 'tue','tues', 'wed', 'thurs', 'thur', 'fri', 'sat' }
months = { 'january':1, 'february':2, 'march':3, 'april':4, 'may':5, 'june':6, 'july':7, 'august':8, 'september':9, 'october':10, 'november':11, 'december':12,
            'jan':1, 'feb':2, 'mar':3, 'apr':4, 'may':5, 'jun':6, 'jul':7, 'aug':8, 'sep':9, 'sept':9, 'oct':10, 'nov':11, 'dec':12}
airlineIATA = { 'delta':'DL', 'american':'AA', 'united':'UA', 'southwest':'WN', 'jetblue':'B6', 'alaska':'AS'}

if __name__ == '__main__':
    start = time.time()
    main()
    end = time.time()
    print(f"Time ellapsed: {round(end - start, 4)} s")