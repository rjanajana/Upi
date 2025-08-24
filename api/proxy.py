from http.server import BaseHTTPRequestHandler
import json
import requests
import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
from urllib.parse import urlparse, parse_qs

# --- Firebase Initialization Logic ---
firebase_initialized = False
def initialize_firebase():
    global firebase_initialized
    if firebase_initialized:
        return True
    try:
        if os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY'):
            service_account_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY'))
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://turnament-c183f-default-rtdb.firebaseio.com'
            })
            firebase_initialized = True
            print("Firebase initialized successfully.")
            return True
        else:
            print("ERROR: FIREBASE_SERVICE_ACCOUNT_KEY environment variable not found.")
            return False
    except Exception as e:
        print(f"Firebase initialization failed: {str(e)}")
        return False

# --- Vercel Standard Handler Class ---
class handler(BaseHTTPRequestHandler):

    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        # Initialize Firebase
        if not initialize_firebase():
            self.send_json_response(503, {
                "error": "Service temporarily unavailable",
                "code": "FIREBASE_ERROR"
            })
            return

        # Parse UID from the URL
        query_components = parse_qs(urlparse(self.path).query)
        uid = query_components.get('uid', [None])[0]

        if not uid:
            self.send_json_response(400, {"error": "UID parameter is required"})
            return

        # --- Dynamic API Call Logic ---
        try:
            print(f"Fetching config for UID: {uid}")
            config_ref = db.reference("config")
            config_data = config_ref.get()

            if not config_data:
                self.send_json_response(500, {"error": "Service configuration not found in Firebase. Please set it in the Admin Panel."})
                return

            api_base_url = config_data.get("apiBaseUrl", "").strip()
            api_endpoint = config_data.get("apiEndpoint", "").strip()

            if not api_base_url or not api_endpoint:
                self.send_json_response(500, {"error": "API URL/Endpoint is not configured. Please set it in the Admin Panel."})
                return

            # Construct the dynamic external API URL
            external_api_url = f"{api_base_url.rstrip('/')}/{uid}/ind/{api_endpoint}"
            print(f"Calling dynamic external API: {external_api_url}")

            # Make the API call
            response = requests.get(
                external_api_url,
                timeout=30,
                headers={'User-Agent': 'Narayana-API-Proxy/3.0'}
            )
            response.raise_for_status()

            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = {"raw_response": response.text}
            
            final_response = {
                "success": True,
                "data": response_data,
                "uid": uid
            }
            self.send_json_response(200, final_response)

        except requests.exceptions.HTTPError as e:
            self.send_json_response(502, {"error": f"External API returned an error: Status {e.response.status_code}"})
        except requests.exceptions.RequestException as e:
            self.send_json_response(504, {"error": f"Could not connect to the external API: {e}"})
        except Exception as e:
            self.send_json_response(500, {"error": f"An internal error occurred: {e}"})

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()