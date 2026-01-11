import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def check_server():
    print(f"Checking {BASE_URL}/health ...")
    try:
        # Check Health
        resp = requests.get(f"{BASE_URL}/health", timeout=3)
        print(f"Health Status: {resp.status_code}")
        print(f"Health Response: {resp.text}")
        
        if resp.status_code != 200:
            print("❌ Server is reachable but returning error.")
            return

        print("✅ Server is UP and responding!")
        
        # Test Upload
        print(f"\nTesting Upload to {BASE_URL}/upload ...")
        files = {'file': ('test.xlsx', b'dummy content', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        resp = requests.post(f"{BASE_URL}/upload", files=files, timeout=5)
        print(f"Upload Status: {resp.status_code}")
        print(f"Upload Response: {resp.text}")

    except requests.exceptions.Timeout:
        print("❌ Timeout! Server is running but NOT responding. (Likely paused in terminal)")
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error! Server is NOT running or port is wrong.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_server()
