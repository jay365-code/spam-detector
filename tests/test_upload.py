
import requests

url = "http://127.0.0.1:8000/upload"
file_path = "sample_kisa_20260107.txt"

payload = {'client_id': 'test_client_001'}
files = [
    ('file', (file_path, open(file_path, 'rb'), 'text/plain'))
]

try:
    response = requests.request("POST", url, data=payload, files=files)
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
