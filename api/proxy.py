from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db
from urllib.parse import urlparse, parse_qs

# --- Vercel Standard Handler Class ---
class handler(BaseHTTPRequestHandler):

    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        # --- CHECKPOINT 1: Kya Vercel ne Secret Key di? ---
        print("--- STARTING API PROXY ---")
        print("Attempting to read environment variable 'FIREBASE_SERVICE_ACCOUNT_KEY'...")
        
        key_json_string = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')

        if key_json_string and len(key_json_string) > 10:
            print("SUCCESS: Environment variable was found!")
            # Hum poori key print nahi karenge, bas shuruaat ke kuch characters
            print(f"Key content starts with: {key_json_string[:50]}...")
        else:
            print("FATAL ERROR: Environment variable was NOT found or is empty.")
            print("Please double-check the variable name and value in Vercel settings.")
            self.send_json_response(500, {
                "error": "Server configuration error: Secret key not found.",
                "code": "ENV_VAR_MISSING"
            })
            return

        # --- CHECKPOINT 2: Kya Key valid JSON hai? ---
        try:
            service_account_info = json.loads(key_json_string)
            print("SUCCESS: Key is valid JSON.")
        except Exception as e:
            print(f"FATAL ERROR: The key is NOT valid JSON. Error: {e}")
            self.send_json_response(500, {
                "error": "Server configuration error: Secret key is malformed.",
                "code": "INVALID_JSON_KEY"
            })
            return

        # --- CHECKPOINT 3: Kya Firebase is key ko accept kar raha hai? ---
        try:
            # Check if already initialized to avoid errors on Vercel's hot reloads
            if not firebase_admin._apps:
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': 'https://turnament-c183f-default-rtdb.firebaseio.com'
                })
            print("SUCCESS: Firebase initialized successfully with the provided key!")
        except Exception as e:
            # YAHAN PAR AAPKA ERROR AA RAHA HAI
            print(f"FATAL ERROR: Firebase rejected the key. Error: {e}")
            self.send_json_response(500, {
                "error": f"Firebase authentication failed: {e}",
                "code": "FIREBASE_AUTH_FAILED"
            })
            return
            
        # Agar yahan tak sab theek hai, to aage ka code chalega
        self.send_json_response(200, {"status": "All checks passed, API is ready."})

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()