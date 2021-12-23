from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/sheets"]

FLIGHT_OVERVIEW_INFO = ["email_id", "err",
                        "name", "confirmation_num", "airline", "cost"]
FLIGHT_SINGLE_INFO = ["flight", "airport1", "airport2",
                      "dep_date", "arr_date", "dep_time", "arr_time", "duration"]


def parse_for_sheet(parsed_result: dict):
    row = [parsed_result.get(c, '') for c in FLIGHT_OVERVIEW_INFO]
    if not (parsed_result.get('flights') and len(parsed_result['flights'])):
        return [row]

    return [row + [f.get(c, '') for c in FLIGHT_SINGLE_INFO] for f in parsed_result["flights"]]


def write_to_sheet(service, sheet_id, results, errs, sheet_idx=0):
    metadata_res = service.spreadsheets().get(spreadsheetId=sheet_id,
                                              fields='sheets(data/rowData/values/userEnteredValue,properties(index,sheetId,title))').execute()
    last_row = len(metadata_res['sheets'][sheet_idx]['data'][0]['rowData'])

    data = []
    if not last_row:
        data.append(FLIGHT_OVERVIEW_INFO + FLIGHT_SINGLE_INFO)

    for dct in results + errs:
        data.extend(parse_for_sheet(dct))

    range = f'A{last_row + 1}:{chr(len(FLIGHT_OVERVIEW_INFO) + len(FLIGHT_SINGLE_INFO)).upper()}{len(data) + 1}'
    res = service.spreadsheets().values().update(spreadsheetId=sheet_id, range=range,
                                                 valueInputOption='RAW', body={'values': data})
    print(res.get('updatedCells'), 'cells updated')


def build_sheets_service(service_acc_info):
    creds = service_account.Credentials.from_service_account_info(
        service_acc_info, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)
