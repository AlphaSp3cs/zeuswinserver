import os
import requests

# Use the credentials from the environment (as set by the script)
api_key = os.environ.get('ALPACA_API_KEY')
secret_key = os.environ.get('ALPACA_SECRET_KEY')
base_url = os.environ.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

print("API Key:", api_key)
print("Secret Key:", secret_key)
print("Base URL:", base_url)

if not api_key or not secret_key:
    print("Missing credentials")
    exit(1)

url = f"{base_url}/v2/account"
headers = {
    'Apca-Api-Key-Id': api_key,
    'Apca-Api-Secret-Key': secret_key
}

print(f"Requesting: {url}")
print("Headers:", headers)

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print(f"Response Headers: {dict(resp.headers)}")
    print(f"Response Body: {resp.text}")
except Exception as e:
    print(f"Exception: {e}")