# Fix for Template Image "Invalid Media Handle" Error

## Problem
You're getting error `2494102: Invalid media handle` even though the media ID looks correct. This happens because of an **endpoint mismatch** between media upload and template creation.

## Root Cause
1. **Media upload endpoints**: The code was trying PAGE_ID first, then WABA_ID, then PHONE_ID
2. **Template creation endpoint**: Templates were being created on PAGE_ID only
3. **Mismatch**: If media was uploaded to WABA_ID/PHONE_ID but template created on PAGE_ID, Facebook rejects it as "invalid media handle"

## Solution Implemented

### 1. Fixed Media Upload Endpoint Order
- **Now tries WABA_ID first** (recommended for templates)
- Then PHONE_ID
- Then PAGE_ID as last resort
- This ensures media is uploaded to the same account where templates are created

### 2. Fixed Template Creation Endpoint
- **Now tries WABA_ID first** (matches media upload)
- Falls back to PAGE_ID if WABA_ID doesn't work
- This ensures consistency between upload and creation endpoints

### 3. Added Better Logging
- Logs which endpoint is used for upload
- Logs which endpoint is used for template creation
- Shows media_id and diagnostic information
- Helps identify endpoint mismatches

### 4. Improved Error Messages
- More detailed error information
- Shows which endpoints were tried
- Provides diagnostic information
- Suggests solutions

## How to Use

### Step 1: Upload Image (NEW - uses WABA_ID first)
```bash
curl -X POST "http://127.0.0.1:8000/templates/upload-header-image" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@image.jpg"
```

**Response:**
```json
{
  "status": "success",
  "media_id": "1234567890",
  "message": "Image uploaded successfully..."
}
```

**Important:** The media will now be uploaded to WABA_ID first, which matches where templates are created.

### Step 2: Create Template IMMEDIATELY (NEW - tries WABA_ID first)
```bash
curl -X POST "http://127.0.0.1:8000/templates/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "appointment_confirmation_image_v1",
    "language": "en_US",
    "category": "UTILITY",
    "allow_category_change": true,
    "components": [
      {
        "type": "HEADER",
        "format": "IMAGE",
        "example": {
          "header_handle": ["1234567890"]
        }
      },
      {
        "type": "BODY",
        "text": "Hello {{1}}, your appointment for {{2}} is confirmed on {{3}}."
      }
    ]
  }'
```

**The template creation will now:**
1. Try WABA_ID endpoint first (matches media upload)
2. Fall back to PAGE_ID if needed
3. Log which endpoint was used
4. Provide better error messages if it fails

## Why This Fixes the Issue

### Before:
- Media uploaded to: WABA_ID or PHONE_ID (after trying PAGE_ID)
- Template created on: PAGE_ID only
- **Result:** Endpoint mismatch → "Invalid media handle" error

### After:
- Media uploaded to: WABA_ID first (then PHONE_ID, then PAGE_ID)
- Template created on: WABA_ID first (then PAGE_ID)
- **Result:** Endpoint consistency → Template creation succeeds

## Debugging

### Check Logs
The code now logs:
```
🔍 Media uploaded successfully to WABA_ID (...), media_id: 1234567890
🔍 Creating template with media ID: 1234567890
🔍 Attempting template creation on WABA_ID: 367633743092037
✅ Template created on WABA_ID
```

### If Still Getting Errors

1. **Check which endpoint was used for upload:**
   - Look for: `Media uploaded successfully to WABA_ID` or `PAGE_ID`
   - This tells you where the media was uploaded

2. **Check which endpoint was used for template creation:**
   - Look for: `Template created on WABA_ID` or `PAGE_ID`
   - This tells you where the template was created

3. **Ensure consistency:**
   - If media uploaded to WABA_ID, template should be created on WABA_ID
   - If media uploaded to PAGE_ID, template should be created on PAGE_ID

4. **If endpoints don't match:**
   - Re-upload the image (it will use WABA_ID first now)
   - Use the new media_id immediately in template creation
   - The template creation will also try WABA_ID first

## Your Specific Case

For your media ID `1171963515039278`:
1. **This media ID was likely uploaded to a different endpoint** than where the template is being created
2. **Solution:** Re-upload the image using the `/templates/upload-header-image` endpoint
3. **Use the new media_id immediately** in template creation
4. **Both operations will now use WABA_ID first**, ensuring consistency

## Additional Notes

- The `allow_category_change` parameter is supported and will be passed through
- All payload parameters are preserved
- Error messages now include diagnostic information
- The code tries multiple endpoints automatically for maximum compatibility

## Testing

1. Upload a new image
2. Check the logs to see which endpoint was used
3. Create template immediately with the new media_id
4. Check the logs to see which endpoint was used
5. Both should use WABA_ID for consistency

If you still get errors, check the logs to see the endpoint mismatch and share the diagnostic information.

