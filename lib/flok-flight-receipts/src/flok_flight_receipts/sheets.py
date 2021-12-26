from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
          "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

FLIGHT_OVERVIEW_INFO = ["id", "err",
                        "name", "confirmation_num", "airline", "cost"]
FLIGHT_SINGLE_INFO = ["flight", "airport1", "airport2",
                      "dep_date", "arr_date", "dep_time", "arr_time", "duration"]

SHEET_TAB_NAME = 'email_intake'  # cannot have spaces
SHEET_TAB_ID = 112233


def parse_for_sheet(parsed_result: dict):
    row = [parsed_result.get(c, '') for c in FLIGHT_OVERVIEW_INFO]
    if not (parsed_result.get('flights') and len(parsed_result['flights'])):
        return [row]

    return [row + [f.get(c, '') for c in FLIGHT_SINGLE_INFO] for f in parsed_result["flights"]]


def write_to_sheet(service, sheet_id, results, errs, sheet_idx=0):
    rows = []
    last_col_name = chr(ord("a") + len(FLIGHT_OVERVIEW_INFO) +
                        len(FLIGHT_SINGLE_INFO)).upper()

    requests = []

    metadata_res = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    if SHEET_TAB_NAME not in [sheet.get('properties', {}).get('title', '') for sheet in metadata_res.get('sheets', [])]:
        # slight bug, if the tab is created wihout the title cols it will not add them ever. not vital though
        # rows.append({'values': [{'userEnteredValue': {'stringValue': c}} for c in FLIGHT_OVERVIEW_INFO + FLIGHT_SINGLE_INFO]})
        rows.append(FLIGHT_OVERVIEW_INFO + FLIGHT_SINGLE_INFO)
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
        # service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={
        #     'requests': [
        #         {
        #             'addSheet': {
        #                 'properties': {
        #                     'title': SHEET_TAB_NAME,
        #                 }
        #             }
        #         }
        #     ]
        # }).execute()

    for dct in results + errs:
        rows.extend(parse_for_sheet(dct))

    for i in range(len(rows)):
        for j in range(len(rows[i])):
            rows[i][j] = {'userEnteredValue': {'stringValue': rows[i][j]}}
        rows[i] = {'values': rows[i]}

    requests.append({
        'appendCells': {
            'rows': rows,
            'sheetId': SHEET_TAB_ID,
            'fields': 'userEnteredValue'
        }
    })

    service.spreadsheets().batchUpdate(spreadsheetId=sheet_id,
                                       body={'requests': requests}).execute()

    # range = f'{SHEET_TAB_NAME}!A1:{last_col_name}'
    # res = service.spreadsheets().values().append(spreadsheetId=sheet_id, range=range, valueInputOption='RAW',
    #  insertDataOption='INSERT_ROWS', body={'range': range, 'majorDimension': 'ROWS', 'values': rows}).execute()


def build_sheets_service(service_acc_info):
    creds = service_account.Credentials.from_service_account_info(
        service_acc_info, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)
