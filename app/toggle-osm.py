# python toggle-osm.py start | toggles the OSM database on the VITALS EC2 instance
# python toggle-osm.py stop | toggles the OSM database off the VITALS EC2 instance
# This script allows you to start or stop the OSM database on the VITALS EC2 instance by sending a request to the API Gateway endpoint.

import requests
import sys

API_ENDPOINT = "https://ikh1sc3052.execute-api.us-east-2.amazonaws.com/default/"

# Development API Key, security is not a concern for this project, but in production this should be stored securely and not hardcoded
API_KEY = "uLvKjXwS1B0uAXh7Uteu6dOJWyCerhx5GW2lrZ64"

def toggle_database(action):
    """Sends a start/stop command to the VITALS OSM EC2 instance."""
    
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {"action": action.lower()}

    try:
        print(f"[*] Sending {action.upper()} request to OSM Database...")
        response = requests.post(API_ENDPOINT, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            print(f"[+] Success: {result.get('status', 'Command executed')}")
        else:
            print(f"[-] Error {response.status_code}: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"[-] Connection failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1].lower() not in ['start', 'stop']:
        print("Usage: python toggle_osm.py [start|stop]")
        sys.exit(1)
        
    toggle_database(sys.argv[1])