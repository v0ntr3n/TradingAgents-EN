import requests
import json

# Configuration
API_KEY = "AIzaSyC3JdZVjblI0rfT_SNXXL5a4kvZ13_12CE"  # Please replace with your real API key
MODEL_NAME = "gemini-2.0-flash"  # Specify the model to use
url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# Request header
headers = {
    "Content-Type": "application/json",
    "x-goog-api-key": API_KEY
}

# Request data
data = {
    "contents": [{
        "parts": [{
            "text": "Please explain artificial intelligence in one sentence."
        }]
    }]
}

# Send request
response = requests.post(url, headers=headers, data=json.dumps(data))

# Handle response
if response.status_code == 200:
    result = response.json()
    print(result['candidates'][0]['content']['parts'][0]['text'])
else:
    print(f"Request failed, status code: {response.status_code}")
    print(response.text)