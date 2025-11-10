# Fix: "Object with ID does not exist" Error

## Problem

You're getting this error when creating templates:

```
Facebook API Error (WABA ID: 367633743092037): {
  'error': {
    'message': "Object with ID '367633743092037' does not exist, cannot be loaded due to missing permissions, or does not support this operation.",
    'code': 100
  }
}
```

## Root Cause

The `WHATSAPP_BUSINESS_ACCOUNT_ID` environment variable is set to `367633743092037`, which is a **Phone Number ID**, not a **WABA ID**.

**Important**: These are different IDs for different purposes:
- **WABA ID** (WhatsApp Business Account ID): Used for template creation
- **Phone ID** (Phone Number ID): Used for sending messages and uploading media

## Solution

### Step 1: Find Your Actual WABA ID

You can find your WABA ID in several ways:

1. **Meta Business Suite**:
   - Go to https://business.facebook.com
   - Navigate to your WhatsApp Business Account
   - The WABA ID is shown in the account settings

2. **Graph API Explorer**:
   - Go to https://developers.facebook.com/tools/explorer/
   - Use your access token
   - Query: `me?fields=whatsapp_business_accounts`
   - Look for the `id` field in the response

3. **From Previous Working Code**:
   - Check your codebase - the original WABA ID was `286831244524604`
   - This might be your correct WABA ID

### Step 2: Set the Correct Environment Variable

Set `WHATSAPP_BUSINESS_ACCOUNT_ID` to your actual WABA ID:

**Windows (PowerShell)**:
```powershell
$env:WHATSAPP_BUSINESS_ACCOUNT_ID="286831244524604"
```

**Windows (Command Prompt)**:
```cmd
set WHATSAPP_BUSINESS_ACCOUNT_ID=286831244524604
```

**Linux/Mac**:
```bash
export WHATSAPP_BUSINESS_ACCOUNT_ID="286831244524604"
```

**In .env file**:
```env
WHATSAPP_BUSINESS_ACCOUNT_ID=286831244524604
WHATSAPP_PHONE_ID=367633743092037
```

### Step 3: Verify Your Configuration

After setting the environment variable, verify:

```python
import os
print("WABA ID:", os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID"))
print("Phone ID:", os.getenv("WHATSAPP_PHONE_ID"))
```

They should be **different** values:
- WABA ID: Used for template operations (e.g., `286831244524604`)
- Phone ID: Used for sending messages (e.g., `367633743092037`)

### Step 4: Test Template Creation

Try creating a template again. It should work now.

## Quick Reference

| ID Type | Purpose | Example | Environment Variable |
|---------|---------|---------|---------------------|
| **WABA ID** | Template creation, template management | `286831244524604` | `WHATSAPP_BUSINESS_ACCOUNT_ID` |
| **Phone ID** | Sending messages, uploading media | `367633743092037` | `WHATSAPP_PHONE_ID` |

## Common Mistakes

❌ **Wrong**: Setting `WHATSAPP_BUSINESS_ACCOUNT_ID=367633743092037` (Phone ID)
✅ **Correct**: Setting `WHATSAPP_BUSINESS_ACCOUNT_ID=286831244524604` (WABA ID)

❌ **Wrong**: Using Phone ID for template creation
✅ **Correct**: Using WABA ID for template creation, Phone ID for sending messages

## Still Having Issues?

If you're still getting errors:

1. **Verify your access token** has permissions for the WABA ID
2. **Check Meta Business Suite** to confirm the WABA ID
3. **Try the Graph API Explorer** to test with your token directly
4. **Check the error message** - it might indicate permission issues

The code now includes validation that will warn you if Phone ID is being used as WABA ID.

