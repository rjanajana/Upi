from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, db
import requests
import os
import logging
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"])  # Configure origins in production

# Initialize Firebase Admin SDK
def initialize_firebase():
    try:
        # For Vercel deployment - use environment variables
        if os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY'):
            service_account_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY'))
            cred = credentials.Certificate(service_account_info)
        else:
            # For local development - use service account file
            cred = credentials.Certificate("path/to/serviceAccountKey.json")
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://turnament-c183f-default-rtdb.firebaseio.com'
        })
        logger.info("Firebase initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Firebase initialization failed: {str(e)}")
        return False

# Initialize Firebase on startup
firebase_initialized = initialize_firebase()

@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Narayana API Proxy",
        "timestamp": datetime.now().isoformat(),
        "firebase_status": "connected" if firebase_initialized else "disconnected"
    }), 200

@app.route("/api/proxy", methods=["GET", "OPTIONS"])
def proxy_api():
    """
    Proxy API endpoint for CORS-safe external API calls
    Expected query params: uid (required)
    Returns: JSON response from external API
    """
    
    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        response = jsonify({"message": "CORS preflight"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
        return response, 200

    try:
        # Validate Firebase connection
        if not firebase_initialized:
            logger.error("Firebase not initialized")
            return jsonify({
                "error": "Service temporarily unavailable",
                "code": "FIREBASE_ERROR"
            }), 503

        # Get and validate UID parameter
        uid = request.args.get("uid", "").strip()
        if not uid:
            logger.warning("Missing UID parameter")
            return jsonify({
                "error": "UID parameter is required",
                "code": "MISSING_UID"
            }), 400

        # Validate UID format (basic validation)
        if not uid.isdigit() or len(uid) < 5:
            logger.warning(f"Invalid UID format: {uid}")
            return jsonify({
                "error": "Invalid UID format. UID should be numeric with at least 5 digits",
                "code": "INVALID_UID"
            }), 400

        # Get configuration from Firebase
        logger.info(f"Fetching config for UID: {uid}")
        config_ref = db.reference("config")
        
        try:
            config_data = config_ref.get()
            if not config_data:
                logger.error("No configuration found in Firebase")
                return jsonify({
                    "error": "Service configuration not found",
                    "code": "CONFIG_NOT_FOUND"
                }), 500
                
            api_base_url = config_data.get("apiBaseUrl", "").strip()
            api_endpoint = config_data.get("apiEndpoint", "").strip()
            
        except Exception as e:
            logger.error(f"Firebase read error: {str(e)}")
            return jsonify({
                "error": "Configuration read failed",
                "code": "FIREBASE_READ_ERROR"
            }), 500

        # Validate configuration
        if not api_base_url or not api_endpoint:
            logger.error(f"Incomplete config - URL: {api_base_url}, Endpoint: {api_endpoint}")
            return jsonify({
                "error": "API configuration incomplete",
                "code": "INCOMPLETE_CONFIG"
            }), 500

        # Construct the external API URL
        # Format: {base_url}/{uid}/ind/{endpoint}
        external_api_url = f"{api_base_url.rstrip('/')}/{uid}/ind/{api_endpoint}"
        logger.info(f"Calling external API: {external_api_url}")

        # Make the external API request with timeout
        try:
            response = requests.get(
                external_api_url,
                timeout=30,  # 30 second timeout
                headers={
                    'User-Agent': 'Narayana-API-Proxy/1.0',
                    'Accept': 'application/json'
                }
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            # Try to parse JSON response
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                # If not JSON, return text response
                response_data = {
                    "message": "External API returned non-JSON response",
                    "data": response.text[:1000],  # Limit response size
                    "status_code": response.status_code
                }

            logger.info(f"Successful API call for UID: {uid}")
            
            # Return successful response with CORS headers
            return jsonify({
                "success": True,
                "data": response_data,
                "uid": uid,
                "timestamp": datetime.now().isoformat(),
                "api_url": external_api_url  # For debugging (remove in production)
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache"
            }

        except requests.exceptions.Timeout:
            logger.error(f"API timeout for URL: {external_api_url}")
            return jsonify({
                "error": "External API request timed out",
                "code": "API_TIMEOUT"
            }), 504

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            logger.error(f"HTTP error {status_code} for URL: {external_api_url}")
            return jsonify({
                "error": f"External API returned error: {status_code}",
                "code": "API_HTTP_ERROR",
                "status_code": status_code
            }), 502

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for URL {external_api_url}: {str(e)}")
            return jsonify({
                "error": "Failed to connect to external API",
                "code": "API_CONNECTION_ERROR"
            }), 502

    except Exception as e:
        logger.error(f"Unexpected error in proxy_api: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@app.route("/api/config", methods=["GET"])
def get_config():
    """Get current configuration (for debugging - remove in production)"""
    try:
        if not firebase_initialized:
            return jsonify({"error": "Firebase not initialized"}), 503
            
        config_ref = db.reference("config")
        config_data = config_ref.get()
        
        # Remove sensitive data
        safe_config = {
            "apiBaseUrl": config_data.get("apiBaseUrl", ""),
            "apiEndpoint": config_data.get("apiEndpoint", ""),
            "hasQrCode": bool(config_data.get("qrCodeUrl", "")),
            "hasContacts": bool(config_data.get("contact", "")),
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(safe_config), 200, {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        }
        
    except Exception as e:
        logger.error(f"Config fetch error: {str(e)}")
        return jsonify({"error": "Failed to fetch configuration"}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "code": "NOT_FOUND",
        "available_endpoints": ["/", "/api/proxy", "/api/config"]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal server error",
        "code": "INTERNAL_ERROR"
    }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
