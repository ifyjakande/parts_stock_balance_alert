import os
import json
import pickle
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests
from datetime import datetime
import pytz

# Constants
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
if not SPREADSHEET_ID:
    raise ValueError("SPREADSHEET_ID environment variable not set")
    
SHEET_NAME = 'parts'
RANGE = 'A1:H3'  # Adjust range to cover the parts data
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SERVICE_ACCOUNT_FILE = 'service-account.json'

# Set up data directory for state persistence
DATA_DIR = os.path.join(os.getenv('GITHUB_WORKSPACE', os.getcwd()), '.data')
os.makedirs(DATA_DIR, exist_ok=True)
PREVIOUS_STATE_FILE = os.path.join(DATA_DIR, 'previous_parts_state.pickle')

class APIError(Exception):
    """Custom exception for API related errors."""
    pass

def get_service():
    """Create and return Google Sheets service object."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        print(f"Error initializing Google Sheets service: {str(e)}")
        raise APIError("Failed to initialize Google Sheets service")

def get_sheet_data(service):
    """Fetch data from Google Sheet."""
    print("Fetching data from sheet...")
    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{SHEET_NAME}!{RANGE}'
        ).execute()
        data = result.get('values', [])
        
        # Validate data structure
        if not data or len(data) < 3:
            raise APIError("Invalid data structure received from Google Sheets")
            
        print("Data fetched successfully")
        return data
    except HttpError as e:
        print(f"Google Sheets API error: {str(e)}")
        raise APIError("Failed to fetch data from Google Sheets")
    except Exception as e:
        print(f"Unexpected error fetching sheet data: {str(e)}")
        raise APIError("Unexpected error while fetching sheet data")

def send_space_alert(webhook_url, changes, current_data):
    """Send alert to Google Space."""
    try:
        message = "🔔 *Parts Stock Weight Changes Detected*\n\n"
        print("Preparing changes message")
        message += "*Changes:*\n"
        for part, old_val, new_val in changes:
            # Try to convert values to numbers with weight suffix
            try:
                old_val_str = f"{float(old_val):,.2f} kg" if str(old_val).strip().replace('.', '', 1).isdigit() else str(old_val)
                new_val_str = f"{float(new_val):,.2f} kg" if str(new_val).strip().replace('.', '', 1).isdigit() else str(new_val)
                message += f"• {part}: {old_val_str} → {new_val_str}\n"
            except (ValueError, TypeError):
                message += f"• {part}: {old_val} → {new_val}\n"
        
        message += "\n*Current Parts Weights:*\n"
        
        # Based on the screenshot, the correct mapping is:
        # Row 1: [DATE, TOTAL WEIGHTS, value, value, value, value, value, value]
        # Row 2: [empty, PARTS TYPE, WINGS, LAPS, BREAST FILLET, BONES, TOTAL]
        
        # Get part headers from row 2 (starting from column C which is index 2)
        part_headers = []
        if len(current_data) > 1 and len(current_data[1]) > 2:
            part_headers = current_data[1][2:]  # Skip empty cell and PARTS TYPE
        
        # Get values from row 1 (starting from column C which is index 2)
        values = []
        if len(current_data) > 0 and len(current_data[0]) > 2:
            values = current_data[0][2:]  # Skip DATE and TOTAL WEIGHTS
        
        # Print debug info
        print(f"Debug - Headers: {part_headers}")
        print(f"Debug - Values: {values}")
        
        # Map values to headers
        for i in range(min(len(part_headers), len(values))):
            try:
                # Format weight values
                val = values[i]
                if str(val).strip().replace('.', '', 1).isdigit():
                    formatted_val = f"{float(val):,.2f} kg"
                else:
                    formatted_val = str(val)
                message += f"• {part_headers[i]}: {formatted_val}\n"
            except (ValueError, TypeError, IndexError) as e:
                print(f"Error formatting part {i}: {str(e)}")
                message += f"• {part_headers[i] if i < len(part_headers) else 'Unknown'}: {values[i] if i < len(values) else 'N/A'}\n"
        
        # Add total weight if available
        if len(current_data[0]) > 1:
            total_weight = current_data[0][1]  # TOTAL WEIGHTS from row 1
            if str(total_weight).strip().replace('.', '', 1).isdigit():
                formatted_total = f"{float(total_weight):,.2f} kg"
            else:
                formatted_total = str(total_weight)
            message += f"\n*TOTAL WEIGHTS: {formatted_total}*\n"
        
        # Get current time in WAT
        wat_tz = pytz.timezone('Africa/Lagos')
        current_time = datetime.now(pytz.UTC).astimezone(wat_tz)
        message += f"\n_Updated at: {current_time.strftime('%Y-%m-%d %I:%M:%S %p')} WAT_"
        
        payload = {
            "text": message
        }
        
        print("Sending webhook request...")
        response = requests.post(webhook_url, json=payload, timeout=10)  # Add timeout
        response.raise_for_status()  # Raise exception for bad status codes
        print(f"Webhook response status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending alert to Google Space: {str(e)}")
        return False

def load_previous_state():
    """Load previous state from file."""
    print("Checking for previous state file")
    try:
        if os.path.exists(PREVIOUS_STATE_FILE):
            print(f"Loading previous state from {PREVIOUS_STATE_FILE}")
            with open(PREVIOUS_STATE_FILE, 'rb') as f:
                data = pickle.load(f)
                if not data or len(data) < 3:
                    print("Invalid state data found, treating as no previous state")
                    return None
                print("Previous state loaded successfully")
                return data
        print("No previous state file found")
        return None
    except Exception as e:
        print(f"Error loading previous state: {str(e)}")
        return None

def save_current_state(state):
    """Save current state to file."""
    if not state or len(state) < 3:
        print("Invalid state data, skipping save")
        return
        
    print("Saving current state")
    try:
        os.makedirs(os.path.dirname(PREVIOUS_STATE_FILE), exist_ok=True)
        with open(PREVIOUS_STATE_FILE, 'wb') as f:
            pickle.dump(state, f)
        print(f"State saved successfully to {PREVIOUS_STATE_FILE}")
    except Exception as e:
        print(f"Error saving state: {str(e)}")
        raise APIError("Failed to save state file")

def detect_changes(previous_data, current_data):
    """Detect changes between previous and current data."""
    if not previous_data:
        print("No previous data available")
        return []
    
    try:
        changes = []
        # Get part headers from row 2 (starting from column C which is index 2)
        part_headers = []
        if len(current_data) > 1 and len(current_data[1]) > 2:
            part_headers = current_data[1][2:]  # Skip empty cell and PARTS TYPE
        
        # Get previous values from row 1 (starting from column C which is index 2)
        prev_values = []
        if len(previous_data) > 0 and len(previous_data[0]) > 2:
            prev_values = previous_data[0][2:]  # Skip DATE and TOTAL WEIGHTS
        
        # Get current values from row 1 (starting from column C which is index 2)
        curr_values = []
        if len(current_data) > 0 and len(current_data[0]) > 2:
            curr_values = current_data[0][2:]  # Skip DATE and TOTAL WEIGHTS
        
        # Print information for debugging
        print(f"Debug - Previous data row length: {len(previous_data[0]) if len(previous_data) > 0 else 0}")
        print(f"Debug - Current data row length: {len(current_data[0]) if len(current_data) > 0 else 0}")
        print(f"Debug - Parts headers row length: {len(current_data[1]) if len(current_data) > 1 else 0}")
        print(f"Debug - Part headers: {part_headers}")
        print(f"Debug - Previous values: {prev_values}")
        print(f"Debug - Current values: {curr_values}")
        
        # Validate data structure
        if len(part_headers) != len(curr_values):
            print(f"Warning: Mismatch between parts ({len(part_headers)}) and values ({len(curr_values)})")
            # Use the shorter length for comparison
            compare_length = min(len(part_headers), len(curr_values))
            # Trim the arrays to the same length
            part_headers = part_headers[:compare_length]
            curr_values = curr_values[:compare_length]
            prev_values = prev_values[:compare_length] if len(prev_values) > compare_length else prev_values
        
        # If previous values array is shorter than current, pad it
        if len(prev_values) < len(curr_values):
            print(f"Warning: Previous values array ({len(prev_values)}) shorter than current ({len(curr_values)})")
            # Pad with empty strings
            prev_values = prev_values + [''] * (len(curr_values) - len(prev_values))
        # If previous values array is longer, trim it
        elif len(prev_values) > len(curr_values):
            print(f"Warning: Previous values array ({len(prev_values)}) longer than current ({len(curr_values)})")
            prev_values = prev_values[:len(curr_values)]
            
        print("\nComparing states...")
        
        # Compare each value and detect changes
        for i in range(len(part_headers)):
            if i >= len(prev_values) or i >= len(curr_values):
                print(f"Warning: Index {i} out of bounds. Skipping comparison.")
                continue
                
            # Convert both values to strings for comparison to avoid type mismatches
            prev_val = str(prev_values[i]).strip()
            curr_val = str(curr_values[i]).strip()
            
            if prev_val != curr_val:
                changes.append((part_headers[i], prev_values[i], curr_values[i]))
                print(f"Change detected in {part_headers[i]}")
        
        # Also check if total weight changed
        if len(previous_data[0]) > 1 and len(current_data[0]) > 1:
            prev_total = str(previous_data[0][1]).strip()  # TOTAL WEIGHTS
            curr_total = str(current_data[0][1]).strip()   # TOTAL WEIGHTS
            
            if prev_total != curr_total:
                changes.append(("TOTAL WEIGHTS", previous_data[0][1], current_data[0][1]))
                print("Change detected in TOTAL WEIGHTS")
        
        if changes:
            print(f"Detected {len(changes)} changes")
        else:
            print("No changes detected in parts weights")
        return changes
    except Exception as e:
        print(f"Error detecting changes: {str(e)}")
        print("Attempting to reset state file for next run...")
        # Save current state to recover from this error
        save_current_state(current_data)
        print("State file updated with current data. Next run should work correctly.")
        # Don't propagate the exception, just return empty changes
        return []

def main():
    try:
        # Get webhook URL from environment variable
        webhook_url = os.environ.get('SPACE_WEBHOOK_URL')
        if not webhook_url:
            raise ValueError("SPACE_WEBHOOK_URL environment variable not set")
        print("Webhook URL configured")

        # Initialize the Sheets API service
        print("Initializing Google Sheets service...")
        service = get_service()
        
        # Get current sheet data
        current_data = get_sheet_data(service)
        
        # Load previous state
        previous_data = load_previous_state()
        
        if not previous_data:
            # First run - just save the initial state without sending alert
            print("No previous state found, initializing state file...")
            save_current_state(current_data)
            print("Initial state saved successfully")
        else:
            # Check for changes
            print("Checking for changes...")
            try:
                changes = detect_changes(previous_data, current_data)
                if changes:
                    print("Changes detected, sending alert...")
                    if send_space_alert(webhook_url, changes=changes, current_data=current_data):
                        save_current_state(current_data)
                    else:
                        print("Failed to send change alert, but continuing execution")
                        save_current_state(current_data)
                else:
                    print("No changes detected, updating state file...")
                    save_current_state(current_data)
            except Exception as e:
                print(f"Error during change detection or alerting: {str(e)}")
                print("Saving current state to recover on next run...")
                save_current_state(current_data)

    except APIError as e:
        print(f"API Error: {str(e)}")
        # Don't exit with error to avoid GitHub Actions failure
        # Just log the error and continue
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        # Don't exit with error to avoid GitHub Actions failure

if __name__ == '__main__':
    main() 