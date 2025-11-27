# Bulk WhatsApp Message Sender

This script reads phone numbers and button URLs from an Excel file and sends WhatsApp template messages to all recipients using the Meta Graph API.

## Prerequisites

1. **WhatsApp Token**: Make sure you have a valid WhatsApp access token stored in the database. You can add it using the API endpoint:
   ```
   POST /whatsapp/token
   Body: { "token": "YOUR_ACCESS_TOKEN" }
   ```

2. **Excel File**: Create an Excel file with the following columns:
   - `phone_number`: Recipient phone number (e.g., `918309866859`)
   - `button_url`: Button URL parameter for the template (e.g., `3WBCRqn`)

## Excel File Format

Your Excel file should look like this:

| phone_number | button_url |
|--------------|------------|
| 918309866859 | 3WBCRqn    |
| 919876543210 | ABC123     |
| 919123456789 | XYZ789     |

**Important Notes:**
- Phone numbers should be in international format without the `+` sign (e.g., `918309866859`)
- The `button_url` column contains the dynamic parameter for the template button
- Empty rows will be skipped

## Usage

### Command Line

```bash
cd wb-crm
python send_bulk_whatsapp.py <path_to_excel_file>
```

### Example

```bash
python send_bulk_whatsapp.py recipients.xlsx
```

## Configuration

You can modify these constants in the script if needed:

- `WHATSAPP_API_URL`: Meta Graph API endpoint (default: `https://graph.facebook.com/v22.0/367633743092037/messages`)
- `TEMPLATE_NAME`: WhatsApp template name (default: `pune_clinic_offer`)
- `TEMPLATE_LANGUAGE`: Template language code (default: `en_US`)
- `IMAGE_ID`: Header image ID (default: `1223826332973821`)

## Output

The script will:
1. Display progress for each message sent
2. Show a summary at the end with success/failure counts
3. Save detailed results to a JSON file (e.g., `recipients_results.json`)

### Example Output

```
✓ Token retrieved from database
✓ Excel file loaded: 10 rows found

Starting to send messages to 10 recipients...
------------------------------------------------------------
📤 Row 1/10: Sending to 918309866859... ✓ Success
📤 Row 2/10: Sending to 919876543210... ✓ Success
...

============================================================
SUMMARY
============================================================
Total recipients: 10
✓ Successful: 10
✗ Failed: 0

Detailed results saved to: recipients_results.json

✓ All messages sent successfully!
```

## Error Handling

- If a phone number is empty or invalid, that row will be skipped
- If a button_url is missing, that row will be skipped
- Failed API calls will be logged with error details
- All errors are saved in the results JSON file

## Template Structure

The script sends messages using this template structure:

```json
{
  "messaging_product": "whatsapp",
  "to": "PHONE_NUMBER",
  "type": "template",
  "template": {
    "name": "pune_clinic_offer",
    "language": { "code": "en_US" },
    "components": [
      {
        "type": "header",
        "parameters": [
          {
            "type": "image",
            "image": { "id": "1223826332973821" }
          }
        ]
      },
      {
        "type": "button",
        "sub_type": "url",
        "index": "1",
        "parameters": [
          {
            "type": "text",
            "text": "BUTTON_URL_PARAM"
          }
        ]
      }
    ]
  }
}
```

## Troubleshooting

1. **"Token not found" error**: Add a token to the database using the `/whatsapp/token` endpoint
2. **"Missing required columns" error**: Ensure your Excel file has `phone_number` and `button_url` columns
3. **API errors**: Check that your token is valid and has the necessary permissions
4. **Rate limiting**: Meta API has rate limits. If you're sending to many recipients, the script will show errors for rate-limited requests

