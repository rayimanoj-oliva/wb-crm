# utils/email_utils.py

import requests
import json
from dotenv import load_dotenv
import os

# Load .env variables
load_dotenv()
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SCOPE = os.getenv("SCOPE")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")


def get_access_token():
    url = f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token'
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': SCOPE,
        'grant_type': 'client_credentials'
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(url, data=payload, headers=headers)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        raise Exception(f"Failed to get token: {response.status_code}, {response.text}")

def send_forgot_password_email(recipient_email: str, reset_link: str):
    token = get_access_token()
    url = f'https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    email_data = {
        "message": {
            "subject": "Password Reset Request",
            "body": {
                "contentType": "HTML",
                "content": f"""
                    <p>Hello,</p>
                    <p>You requested to reset your password. Click the link below:</p>
                    <p><a href="{reset_link}">Reset Password</a></p>
                    <p>This link will expire soon. If you did not request a reset, please ignore this email.</p>
                """
            },
            "toRecipients": [
                {"emailAddress": {"address": recipient_email}}
            ]
        },
        "saveToSentItems": "true"
    }
    response = requests.post(url, headers=headers, data=json.dumps(email_data))
    if response.status_code == 202:
        return True
    else:
        raise Exception(f"Failed to send email: {response.status_code}, {response.text}")
