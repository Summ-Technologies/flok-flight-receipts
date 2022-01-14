from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
          "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

MISC_COLS = ["processed"]
FLIGHT_OVERVIEW_INFO = ["id", "address", "subject", "err",
                        "name", "confirmation_num", "airline", "cost"]
FLIGHT_SINGLE_INFO = ["flight", "airport1", "airport2",
                      "dep_date", "arr_date", "dep_time", "arr_time", "duration"]

SHEET_TAB_NAME = 'email_intake'  # cannot have spaces
SHEET_TAB_ID = 112233

UNCHECKED_BOOLEAN_CELL = {
    "dataValidation": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True},
}

def get_gmail_link_cell(emailId: str):
    """Sets cell value for id column that has link to email"""
    return {
        "userEnteredValue": {"stringValue": emailId},
        "textFormatRuns": [
            {
                "startIndex": 0,
                "format": {
                    "link": {"uri": f"https://mail.google.com/#all/{emailId}"}
                }
            }
        ]
    }


def parse_for_sheet(parsed_result: dict):
    row = [parsed_result.get(c, '') for c in FLIGHT_OVERVIEW_INFO]
    if not (parsed_result.get('flights') and len(parsed_result['flights'])):
        return [row]

    return [row + [f.get(c, '') for c in FLIGHT_SINGLE_INFO] for f in parsed_result["flights"]]


def write_to_sheet(service, sheet_id, results, errs, sheet_idx=0):
    """This method will add a falsey check box to the start of each row."""
    rows = []
    requests = []
    add_header = False

    metadata_res = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    if SHEET_TAB_NAME not in [sheet.get('properties', {}).get('title', '') for sheet in metadata_res.get('sheets', [])]:
        # slight bug, if the tab is created wihout the title cols it will not add them ever. not vital though
        add_header = True
        rows.append( MISC_COLS + FLIGHT_OVERVIEW_INFO + FLIGHT_SINGLE_INFO)
        requests.append(
            {
                'addSheet': {
                    'properties': {
                        'title': SHEET_TAB_NAME,
                        'sheetId': SHEET_TAB_ID
                    }
                }
            }
        )

    for dct in results + errs:
        rows.extend(parse_for_sheet(dct))

    for i in range(len(rows)):
        for j in range(len(rows[i])):
            if j == 0 and (not add_header or i != 0) and rows[i][j]:
                rows[i][j] = get_gmail_link_cell(rows[i][j])
            else:
                rows[i][j] = {'userEnteredValue': {'stringValue': rows[i][j]}}
        if add_header and i == 0:
            rows[i] = {'values': rows[i]}
        else:
            rows[i] = {'values': [UNCHECKED_BOOLEAN_CELL] + rows[i]}

    requests.append({
        'appendCells': {
            'rows': rows,
            'sheetId': SHEET_TAB_ID,
            'fields': 'userEnteredValue,dataValidation,textFormatRuns'
        }
    })

    service.spreadsheets().batchUpdate(spreadsheetId=sheet_id,
                                       body={'requests': requests}).execute()


def build_sheets_service(service_acc_info):
    creds = service_account.Credentials.from_service_account_info(
        service_acc_info, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)
