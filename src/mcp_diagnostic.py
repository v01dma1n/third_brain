import os
import sys
import json
import requests

def run_diagnostic():
    url = "https://mipngawystbrkymvfhfx.supabase.co/functions/v1/open-brain-mcp"
    access_key = os.environ.get("MCP_ACCESS_KEY")

    if not access_key:
        print("Error: MCP_ACCESS_KEY environment variable is not set.")
        sys.exit(1)

    headers = {
        "x-brain-key": access_key,
        "Content-Type": "application/json"
    }

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "diagnostic-script",
                "version": "1.0.0"
            }
        }
    }

    print("Sending POST request to Edge Function...")
    
    try:
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=10)
        
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code == 401:
            print("Failure: 401 Unauthorized. The x-brain-key does not match the Supabase secret.")
        elif response.status_code == 405:
            print("Failure: 405 Method Not Allowed. The endpoint expects a POST request.")
        elif response.status_code == 200:
            print("Success: 200 OK. Authentication passed and stream opened.")
            
            # Read the first line of the Server-Sent Events (SSE) stream to confirm JSON-RPC response
            for line in response.iter_lines():
                if line:
                    print(f"Stream output: {line.decode('utf-8')}")
                    break
        else:
            print(f"Unexpected response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")

if __name__ == "__main__":
    run_diagnostic()
