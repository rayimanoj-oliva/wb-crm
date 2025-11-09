# Guide: Creating WhatsApp Templates with Images

## Why Templates with Images Require Special Handling

### The Problem
WhatsApp Business API requires a **two-step process** for templates with images:
1. **Upload the image first** → Get a temporary media ID
2. **Create the template immediately** → Use the media ID before it expires

### Why This Is Necessary
- **Media IDs are temporary**: Facebook/WhatsApp media IDs expire quickly (often within minutes)
- **Template validation**: WhatsApp validates that the image exists when you submit the template
- **No direct file upload**: You cannot attach image files directly in the template creation request
- **Separation of concerns**: Media upload and template creation are separate API endpoints

## Step-by-Step Process

### Step 1: Upload the Image
**Endpoint**: `POST /templates/upload-header-image`

**Request**: 
- Method: POST
- Content-Type: multipart/form-data
- Body: File upload (image file)

**Response**:
```json
{
  "status": "success",
  "media_id": "1234567890",
  "message": "Image uploaded successfully...",
  "usage": {
    "component_type": "HEADER",
    "format": "IMAGE",
    "example": {
      "header_handle": ["1234567890"]
    }
  }
}
```

### Step 2: Create Template (IMMEDIATELY)
**Endpoint**: `POST /templates/`

**Request Body**:
```json
{
  "name": "my_template_with_image",
  "language": "en_US",
  "category": "MARKETING",
  "components": [
    {
      "type": "HEADER",
      "format": "IMAGE",
      "example": {
        "header_handle": ["1234567890"]  // Use the media_id from Step 1
      }
    },
    {
      "type": "BODY",
      "text": "Hello {{1}}, check out our new product!"
    }
  ]
}
```

## Common Issues & Solutions

### Issue 1: "Invalid media handle" Error
**Error Code**: 2494102

**Causes**:
- Media ID expired (too much time between upload and template creation)
- Media ID format incorrect
- Media ID from wrong WhatsApp Business Account

**Solutions**:
1. ✅ Upload the image and create the template **immediately** (within 1-2 minutes)
2. ✅ Verify the media_id is a string in an array: `["media_id"]`
3. ✅ Ensure you're using the same WhatsApp Business Account for both operations
4. ✅ Re-upload the image if you get this error

### Issue 2: Image Upload Fails
**Possible Causes**:
- Invalid image format (must be JPG, PNG, or WebP)
- Image too large (WhatsApp has size limits)
- Invalid access token
- Wrong endpoint (PAGE_ID vs PHONE_ID vs WABA_ID)

**Solutions**:
1. ✅ Use supported formats: JPG, PNG, WebP
2. ✅ Keep image size under 5MB (recommended)
3. ✅ Verify your WhatsApp access token is valid
4. ✅ The code tries multiple endpoints automatically (PAGE_ID → WABA_ID → PHONE_ID)

### Issue 3: Template Creation Succeeds But Image Doesn't Show
**Possible Causes**:
- Image was deleted after template creation
- Template is in pending/approval status
- Wrong media ID format in the payload

**Solutions**:
1. ✅ Wait for template approval (can take 24-48 hours)
2. ✅ Verify the template status using `/templates/meta` endpoint
3. ✅ Check that `header_handle` is an array with one string element

## Image Requirements

### Supported Formats
- JPEG/JPG
- PNG
- WebP

### Size Limits
- **Recommended**: Under 5MB
- **Maximum**: Check WhatsApp Business API documentation for current limits

### Dimensions
- **Recommended**: 800x418 pixels (aspect ratio ~1.91:1)
- WhatsApp will automatically resize, but this ratio works best

## Complete Example Workflow

### Using cURL

**1. Upload Image**:
```bash
curl -X POST "http://localhost:8000/templates/upload-header-image" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/image.jpg"
```

**Response**:
```json
{
  "media_id": "123456789012345",
  "status": "success"
}
```

**2. Create Template (IMMEDIATELY)**:
```bash
curl -X POST "http://localhost:8000/templates/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "welcome_promo",
    "language": "en_US",
    "category": "MARKETING",
    "components": [
      {
        "type": "HEADER",
        "format": "IMAGE",
        "example": {
          "header_handle": ["123456789012345"]
        }
      },
      {
        "type": "BODY",
        "text": "Welcome {{1}}! Enjoy {{2}}% off your first order."
      },
      {
        "type": "FOOTER",
        "text": "Limited time offer"
      }
    ]
  }'
```

### Using Python

```python
import requests

# Step 1: Upload image
with open("image.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/templates/upload-header-image",
        files={"file": f},
        headers={"Authorization": "Bearer YOUR_TOKEN"}
    )
media_id = response.json()["media_id"]

# Step 2: Create template IMMEDIATELY
template_payload = {
    "name": "welcome_promo",
    "language": "en_US",
    "category": "MARKETING",
    "components": [
        {
            "type": "HEADER",
            "format": "IMAGE",
            "example": {
                "header_handle": [media_id]  # Use the media_id from Step 1
            }
        },
        {
            "type": "BODY",
            "text": "Welcome {{1}}! Enjoy {{2}}% off your first order."
        }
    ]
}

response = requests.post(
    "http://localhost:8000/templates/",
    json=template_payload,
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
print(response.json())
```

## Validation Endpoint

You can validate if a media ID is still valid before using it:

**Endpoint**: `GET /templates/validate-media/{media_id}`

**Response**:
```json
{
  "media_id": "1234567890",
  "valid": true,
  "message": "Media ID is valid"
}
```

## Best Practices

1. ✅ **Upload and create immediately**: Don't wait between upload and template creation
2. ✅ **Handle errors gracefully**: If media ID expires, re-upload the image
3. ✅ **Validate media IDs**: Use the validation endpoint if you're unsure
4. ✅ **Optimize images**: Compress images before uploading to reduce upload time
5. ✅ **Test with small images first**: Verify the workflow works before using production images
6. ✅ **Monitor template status**: Templates need approval before they can be used

## Troubleshooting Checklist

- [ ] Is the image format supported? (JPG, PNG, WebP)
- [ ] Is the image size reasonable? (< 5MB recommended)
- [ ] Did you upload the image first?
- [ ] Did you create the template immediately after upload?
- [ ] Is the media_id in the correct format? `["media_id"]` (array with one string)
- [ ] Is your WhatsApp access token valid?
- [ ] Are you using the same WhatsApp Business Account for both operations?
- [ ] Did you wait for template approval? (can take 24-48 hours)

## Code Flow in This Codebase

1. **Upload** (`upload_image_for_template_header`):
   - Tries PAGE_ID endpoint first
   - Falls back to WABA_ID if that fails
   - Falls back to PHONE_ID as last resort
   - Returns media_id

2. **Create Template** (`send_template_to_facebook`):
   - Normalizes the payload format
   - Ensures `header_handle` is an array of strings
   - Sends to Facebook API
   - Handles error 2494102 (invalid media handle) with helpful message
   - Saves template to local database

3. **Validation** (`validate_media_id`):
   - Checks if media ID is still accessible
   - Useful for debugging

## Why Media IDs Expire

Media IDs are temporary because:
- **Security**: Prevents unauthorized access to uploaded media
- **Storage**: WhatsApp doesn't want to store unused media indefinitely
- **Performance**: Reduces storage overhead
- **API Design**: Encourages immediate use of uploaded media

This is why you must create the template **immediately** after uploading the image.

