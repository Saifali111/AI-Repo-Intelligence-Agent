import requests
import os
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def send_to_slack(briefing_text):
    payload = {
        "text": f"*🌅 DevPulse Morning Briefing*\n\n{briefing_text}"
    }
    
    response = requests.post(SLACK_WEBHOOK_URL, json=payload)
    
    if response.status_code == 200:
        print("Briefing sent to Slack successfully.")
    else:
        print(f"Failed to send to Slack. Status: {response.status_code}, Response: {response.text}")

if __name__ == "__main__":
    test_message = "This is a test briefing from DevPulse."
    send_to_slack(test_message)