# 📱 Complete Guide: Send Bulk WhatsApp Messages

## 🚀 Quick Start (3 Steps)

### Step 1: Activate Virtual Environment
```powershell
cd D:\Downloads\oliva-codebase\crm\wb-crm
.\venv\Scripts\Activate.ps1
```
You should see `(venv)` in your prompt.

### Step 2: Prepare Excel File
Create an Excel file with these columns:

| phone_number | button_url |
|--------------|------------|
| 918309866859 | 3WBCRqn    |
| 919876543210 | ABC123     |

**Save it in the `wb-crm` folder** (e.g., `recipients.xlsx`)

### Step 3: Run the Script
```powershell
python send_bulk_whatsapp.py recipients.xlsx
```

That's it! 🎉

---

## 📋 Detailed Instructions

### Method 1: Using Python Directly (Recommended)

```powershell
# 1. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 2. Run the script
python send_bulk_whatsapp.py recipients.xlsx
```

### Method 2: Using PowerShell Helper Script

```powershell
# No need to activate venv manually - the script does it for you!
.\send_bulk_whatsapp.ps1 -ExcelFile "recipients.xlsx"
```

### Method 3: With Custom Options

```powershell
python send_bulk_whatsapp.py recipients.xlsx `
    --template-name "pune_clinic_offer" `
    --image-id "1223826332973821" `
    --template-language "en_US"
```

---

## 📊 Excel File Format

Your Excel file **MUST** have these exact column names:

| phone_number | button_url |
|--------------|------------|
| 918309866859 | 3WBCRqn    |
| 919876543210 | ABC123     |
| 919123456789 | XYZ789     |

**Important:**
- ✅ Column names: `phone_number` and `button_url` (exact match, case-sensitive)
- ✅ Phone format: International without `+` (e.g., `918309866859`)
- ✅ File format: `.xlsx` or `.xls`
- ❌ Don't include headers like "Phone Number" or "Button URL" - use exact names above

---

## ⚙️ Prerequisites

### 1. WhatsApp Token in Database
Make sure you have a valid token. Add it via API:

```bash
POST http://localhost:8000/whatsapp/token
Content-Type: application/json

{
  "token": "YOUR_ACCESS_TOKEN_HERE"
}
```

Or use your existing token from Postman.

### 2. Virtual Environment Activated
Always activate before running:
```powershell
.\venv\Scripts\Activate.ps1
```

---

## 📤 What Happens When You Run

1. **Token Check** - Retrieves WhatsApp token from database
2. **Excel Reading** - Loads your Excel file
3. **Validation** - Checks for required columns
4. **Sending** - Sends message to each phone number
5. **Progress** - Shows real-time progress
6. **Results** - Saves detailed results to JSON file

### Example Output:
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

---

## 🔧 Configuration Options

### Default Values (matches your Postman request):
- **Template Name:** `pune_clinic_offer`
- **Language:** `en_US`
- **Image ID:** `1223826332973821`
- **API URL:** `https://graph.facebook.com/v22.0/367633743092037/messages`

### Customize via Command Line:
```powershell
python send_bulk_whatsapp.py recipients.xlsx `
    --template-name "my_template" `
    --image-id "123456789" `
    --template-language "hi_IN" `
    --api-url "https://graph.facebook.com/v22.0/YOUR_PHONE_ID/messages"
```

---

## 🐛 Troubleshooting

### ❌ "ModuleNotFoundError: No module named 'pandas'"
**Fix:** Activate virtual environment:
```powershell
.\venv\Scripts\Activate.ps1
```

### ❌ "WhatsApp token not found in database"
**Fix:** Add token via API endpoint `/whatsapp/token`

### ❌ "Missing required columns in Excel"
**Fix:** Ensure columns are named exactly: `phone_number` and `button_url`

### ❌ "File not found"
**Fix:** Use full path or ensure file is in `wb-crm` directory:
```powershell
python send_bulk_whatsapp.py "C:\Users\YourName\recipients.xlsx"
```

### ❌ API Errors (Rate Limiting, Invalid Token, etc.)
**Fix:** 
- Check token is valid and not expired
- Wait a few minutes if rate limited
- Check phone number format (no +, international format)

---

## 📁 Output Files

After running, you'll get:
- **Console output** - Real-time progress and summary
- **JSON results file** - Detailed results (e.g., `recipients_results.json`)

The JSON file contains:
- Success/failure status for each recipient
- Error messages if any
- Message IDs for successful sends

---

## ✅ Complete Example

```powershell
# 1. Navigate to directory
cd D:\Downloads\oliva-codebase\crm\wb-crm

# 2. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 3. Verify Excel file exists
dir recipients.xlsx

# 4. Run the script
python send_bulk_whatsapp.py recipients.xlsx

# 5. Check results
dir recipients_results.json
```

---

## 🎯 Quick Reference

| Command | Description |
|---------|-------------|
| `.\venv\Scripts\Activate.ps1` | Activate virtual environment |
| `python send_bulk_whatsapp.py file.xlsx` | Send messages |
| `python send_bulk_whatsapp.py --help` | Show all options |
| `.\send_bulk_whatsapp.ps1 -ExcelFile file.xlsx` | Use helper script |

---

## 📞 Need Help?

1. Check `QUICK_START_GUIDE.md` for basics
2. Check `BULK_WHATSAPP_README.md` for detailed docs
3. Run `python send_bulk_whatsapp.py --help` for options

