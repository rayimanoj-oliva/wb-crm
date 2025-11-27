# 🔧 Troubleshooting 400 Bad Request Errors

## Common Causes of 400 Errors

### 1. **Invalid Phone Number Format**
WhatsApp requires phone numbers in international format without `+`:
- ✅ Correct: `918862075288` (India: 91 + number)
- ❌ Wrong: `+918862075288` (has +)
- ❌ Wrong: `8862075288` (missing country code)
- ❌ Wrong: `918862075288` with spaces

**Fix:** Ensure phone numbers are exactly: `country_code + number` (no +, no spaces)

### 2. **Invalid Template Name**
The template must:
- ✅ Be approved and active in Meta Business Manager
- ✅ Match exactly (case-sensitive)
- ✅ Be available for your WhatsApp Business Account

**Fix:** 
- Check template name in Meta Business Manager
- Verify it's approved and active
- Use exact name (case-sensitive)

### 3. **Invalid Button Parameter**
Button URL parameters must:
- ✅ Match the template's button variable format
- ✅ Be valid URL-safe text
- ✅ Not exceed length limits

**Fix:**
- Check your template in Meta Business Manager
- Verify button parameter format
- Ensure button_url values are valid

### 4. **Invalid Image ID**
The header image ID must:
- ✅ Be a valid media ID from Meta
- ✅ Be uploaded to your WhatsApp Business Account
- ✅ Not be expired

**Fix:**
- Re-upload image if needed
- Verify image ID is correct
- Check image hasn't expired

### 5. **Template Not Approved**
Template must be:
- ✅ Approved by Meta
- ✅ Active (not paused/rejected)
- ✅ Available for your account

**Fix:**
- Check template status in Meta Business Manager
- Wait for approval if pending
- Fix any rejection issues

## 🔍 How to Debug

### Step 1: Check Error Details
The script now shows detailed error messages. Look for:
```
✗ Failed: [Error Code] Error message
   Full error: ...
   Error type: ...
   Error subcode: ...
```

### Step 2: Test with Single Recipient
Test with one phone number first:
```powershell
# Create test file with 1 row
python send_bulk_whatsapp.py test_recipient.xlsx
```

### Step 3: Verify Template
1. Go to Meta Business Manager
2. Check template `pune_clinic_offer`
3. Verify it's approved and active
4. Check button parameter format

### Step 4: Check Phone Numbers
Verify phone numbers in your Excel:
- Must have country code (e.g., 91 for India)
- No + sign
- No spaces or special characters
- Valid format: `91XXXXXXXXXX`

### Step 5: Verify Button URL Parameter
Check your Excel `button_url` column:
- Values should match template requirements
- No invalid characters
- Correct format for URL button

## 🛠️ Quick Fixes

### Fix 1: Validate Phone Numbers
```python
# Phone should be: country_code + number
# Example: 918862075288 (91 = India, 8862075288 = number)
```

### Fix 2: Check Template Status
1. Login to Meta Business Manager
2. Go to WhatsApp > Message Templates
3. Find `pune_clinic_offer`
4. Verify status is "Approved" and "Active"

### Fix 3: Verify Image ID
The image ID `1223826332973821` must be:
- Valid in your account
- Not expired
- Accessible

### Fix 4: Test Button Parameter
Try with a known working button parameter:
- Use the same format as your Postman test
- Verify it matches template requirements

## 📋 Common Error Codes

| Error Code | Meaning | Fix |
|------------|---------|-----|
| 100 | Invalid parameter | Check phone number format |
| 131047 | Template not found | Verify template name |
| 131051 | Template not approved | Wait for approval |
| 131026 | Invalid button parameter | Check button format |
| 131031 | Invalid media ID | Re-upload image |

## 🔄 Next Steps

1. **Check the detailed error** - Script now shows full error messages
2. **Verify template** - Ensure it's approved in Meta
3. **Check phone format** - Must be international without +
4. **Test single recipient** - Isolate the issue
5. **Review button parameter** - Match template requirements

## 💡 Prevention

- ✅ Always test with 1-2 recipients first
- ✅ Verify template is approved before bulk sending
- ✅ Check phone number format in Excel
- ✅ Validate button parameters match template
- ✅ Keep image IDs up to date

---

**The improved error handling will now show you exactly what's wrong!** 🔍

