from __future__ import print_function
import pickle
import re
import os.path
import nltk
# nltk.download('punkt')
# nltk.download('averaged_perceptron_tagger')
# nltk.download('maxent_ne_chunker')
# nltk.download('words')
from datetime import date, time
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from base64 import urlsafe_b64decode as decode
from bs4 import BeautifulSoup

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# user
_userId = 'testflok0@gmail.com'

def main():
    # parts = fetchEmailHtml(5)
    # print(getTextString(parts[1]))
    confirmation = None
    airport1, airport2, flight_1, flight_2, name = None, None, None, None, None
    arr1_date, arr2_date, dep1_date, dep2_date = None, None, None, None
    arr1_time, arr2_time, dep1_time, dep2_time = None, None, None, None
    word_count = dict()
    
    f = open("data/alaska1.txt")
    email = unicodetoascii(f.read())
    email = email.replace('–', ' ').split()
    for i in range(len(email)):
        # find flights
        # find dates
        if isValidDate(email, i):
            if dep1_date == None:
                dep1_date = " ".join(email[i:i+3])
            elif dep2_date == None:
                dep2_date = " ".join(email[i:i+3])
        # find times
        if isValidTime(email, i):
            time = email[i].lower()
            if 'am' in time:
                time = email[i:time.find('am')] + " AM" 
            elif 'pm' in time:
                time = email[i:time.find('pm')] + " PM"
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
        # find cost
        # find other info
        if email[i].lower() in {'passenger:', 'name:', 'traveler details'} and i < len(email) - 2 and name == None:
            print(" ".join(email[i+1:i+3]))
            name = " ".join(email[i+1:i+3])
        # other
        if email[i] in word_count:
            word_count[email[i]] += 1
        else:
            word_count[email[i]] = 1
    
    # print(extract_names(" ".join(email)))
    # summary
    print(
        f"Passenger: {name}   Confirmation Number: {confirmation}\n"
        f"========================================================\n"
        f"Flight {flight_1} from {airport1} to {airport2}\n\n"
        f"Departs on {dep1_date} at {dep1_time}\nArrives at {arr1_time}\n\n"
        f"--------------------------------------------------------\n"
        f"Flight {flight_2} from {airport2} to {airport1}\n\n"
        f"Departs on {dep2_date} at {dep2_time}\nArrives at {arr2_time}\n\n"
        f"========================================================\n"
    )

def isValidTime(email, i):
    if ':' not in email[i]:
        return False
    pattern = '([0-9]{1,2}:[0-9][0-9])([aA]|[pP]m){0,1}'
    if bool(re.match(pattern, email[i])):
        return True


def isValidDate(email, i):
    if i > len(email) - 3:
        return False
    day, month, number = email[i].lower(), email[i+1].lower(), email[i+2].lower()
    if day[:-1] in days and day[-1] == ',' and month in months:
        if number[-1] == ',':
            number = number[:-1]
        if number.isnumeric() and int(number) > 0 and int(number) < 32:
            return True
        else:
            return False
    else:
        return False

def getTextString(part):
    html = decode(part["body"]["data"])
    soup = BeautifulSoup(html, "lxml")

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

# utility
days = { 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday',
        'sun', 'mon', 'tues', 'wed', 'thurs', 'fri', 'sat' }
months = { 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
            'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec'}

def extract_names(text):
    ppl = []
    for sent in nltk.sent_tokenize(text):
        for chunk in nltk.ne_chunk(nltk.pos_tag(nltk.word_tokenize(sent))):
            if hasattr(chunk, 'label') and chunk.label() == "PERSON" and len(chunk.leaves()) > 1:
                ppl.append(' '.join([c[0] for c in chunk.leaves()]))
    ppl = [name for name in ppl if heuristic(name)]

    return ppl

def heuristic(name):
    name = name.lower()
    keywords = ['airport', 'alaska', 'jetblue']
    return all([word not in name for word in keywords])

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
            replace('\\xe2\\x80\\xa6', '...')
            # replace('\\xe2\\x80\\xb2', "'").
            # replace('\\xe2\\x80\\xb3', "'").
            # replace('\\xe2\\x80\\xb4', "'").
            # replace('\\xe2\\x80\\xb5', "'").
            # replace('\\xe2\\x80\\xb6', "'").
            # replace('\\xe2\\x80\\xb7', "'").
            # replace('\\xe2\\x81\\xba', "+").
            # replace('\\xe2\\x81\\xbb', "-").
            # replace('\\xe2\\x81\\xbc', "=").
            # replace('\\xe2\\x81\\xbd', "(").
            # replace('\\xe2\\x81\\xbe', ")")
            )
    return TEXT

def strip(txt):
	return txt.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').replace('    ', ' ').replace('  ', ' ').replace('  ', ' ').replace('   ', ' ').strip()

if __name__ == '__main__':
    main()