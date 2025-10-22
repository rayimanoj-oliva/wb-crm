# WhatsApp Webhook Troubleshooting Guide

## Issue: JSON Truncation in Webhook Logs

### Problem Description
The webhook logs show truncated JSON data, particularly in the `response_json` field of `nfm_reply` messages. This happens when the webhook payload is not captured completely before processing.

### Root Causes
1. **Request Body Consumption**: The original code called `await request.json()` first, which can consume the request body stream
2. **Incomplete Logging**: The logging mechanism was trying to serialize already-parsed JSON instead of capturing raw data
3. **Missing Error Handling**: No validation for truncated or malformed JSON payloads

### Solutions Implemented

#### 1. Raw Body Capture (CRITICAL FIX)
```python
# BEFORE (problematic):
body = await request.json()
# ... logging code ...

# AFTER (fixed):
raw_body = await request.body()
raw_body_str = raw_body.decode("utf-8", errors="replace")
body = json.loads(raw_body_str)
```

#### 2. Enhanced Logging
- **Raw Log**: Complete unprocessed webhook payload
- **Formatted Log**: Pretty-printed JSON for debugging
- **Debug Function**: Comprehensive payload analysis

#### 3. Improved NFM Reply Handling
- Enhanced error handling for JSON parsing
- Better validation of response data
- Detailed logging for debugging

### Steps to Avoid Truncation Issues

#### 1. Always Capture Raw Body First
```python
@router.post("/webhook")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    # CRITICAL: Capture raw body BEFORE any processing
    raw_body = await request.body()
    raw_body_str = raw_body.decode("utf-8", errors="replace")
    
    # Parse JSON from raw body
    try:
        body = json.loads(raw_body_str)
    except json.JSONDecodeError as e:
        # Handle invalid JSON
        return {"status": "error", "message": "Invalid JSON payload"}
```

#### 2. Implement Comprehensive Logging
```python
# Log both raw and formatted versions
log_path = os.path.join(log_dir, f"webhook_{ts}.json")
with open(log_path, "w", encoding="utf-8") as lf:
    lf.write(raw_body_str)  # Complete raw data

# Formatted version for debugging
formatted_path = os.path.join(log_dir, f"webhook_{ts}_formatted.json")
formatted_json = json.dumps(body, ensure_ascii=False, indent=2, default=str)
with open(formatted_path, "w", encoding="utf-8") as lf:
    lf.write(formatted_json)
```

#### 3. Add Debug Validation
```python
def debug_webhook_payload(body: Dict[str, Any], raw_body: str = None):
    """Enhanced debugging utility for webhook payloads"""
    # Check for truncation indicators
    if response_json.endswith('...') or len(response_json) < 50:
        print(f"[webhook_debug] WARNING - Possible truncation detected!")
    
    # Validate JSON structure
    try:
        parsed = json.loads(response_json)
        print(f"[webhook_debug] NFM parsed keys: {list(parsed.keys())}")
    except json.JSONDecodeError as e:
        print(f"[webhook_debug] ERROR - Invalid JSON: {e}")
```

#### 4. Enhanced Error Handling
```python
# Validate response data
if not response_data or (isinstance(response_data, dict) and not any(response_data.values())):
    print(f"[webhook_debug] WARNING - Empty or invalid response data")
    await send_message_to_waid(wa_id, "❌ No data received from the form. Please try again.", db)
    return {"status": "empty_form_data", "message_id": message_id}

# Check for template variables (indicates flow token issues)
has_template_vars = any("{{" in str(v) and "}}" in str(v) for v in response_data.values())
if has_template_vars:
    print(f"[webhook_debug] WARNING - Received template variables instead of actual values")
    await send_message_to_waid(wa_id, "❌ The address form wasn't filled out properly. Please try again.", db)
    return {"status": "form_not_filled", "message_id": message_id}
```

### Monitoring and Prevention

#### 1. Log Analysis
- Check webhook logs for truncation indicators
- Monitor response_json length and content
- Look for incomplete JSON structures

#### 2. Flow Token Validation
- Ensure flow tokens are properly generated and stored
- Validate token format and expiration
- Check for token mismatches

#### 3. Error Recovery
- Implement automatic retry mechanisms
- Provide user-friendly error messages
- Log detailed error information for debugging

### Testing Checklist

- [ ] Webhook receives complete JSON payload
- [ ] Raw body is captured before processing
- [ ] Logs contain complete data (no truncation)
- [ ] NFM replies are properly parsed
- [ ] Error handling works for malformed data
- [ ] Flow tokens are validated correctly
- [ ] User receives appropriate feedback

### Common Issues and Solutions

#### Issue: "Template variables detected"
**Cause**: Flow token mismatch or expired token
**Solution**: Regenerate flow token and resend form

#### Issue: "Empty form data"
**Cause**: User didn't fill out the form properly
**Solution**: Send error message and resend form

#### Issue: "JSON parse error"
**Cause**: Truncated or malformed JSON
**Solution**: Check webhook logging and request body capture

#### Issue: "Invalid JSON payload"
**Cause**: WhatsApp sent malformed data
**Solution**: Log raw body and contact WhatsApp support

### Best Practices

1. **Always capture raw body first** before any JSON parsing
2. **Implement comprehensive logging** for debugging
3. **Add validation** for all webhook data
4. **Handle errors gracefully** with user feedback
5. **Monitor webhook health** regularly
6. **Test with various payload sizes** to ensure no truncation
7. **Keep logs for debugging** but clean up old ones periodically

### Debug Commands

```bash
# Check webhook logs for truncation
grep -r "WARNING.*truncation" webhook_logs/

# Check for incomplete JSON
grep -r "response_json.*\.\.\." webhook_logs/

# Monitor webhook payload sizes
ls -la webhook_logs/ | awk '{print $5, $9}' | sort -n

# Check for template variables
grep -r "{{.*}}" webhook_logs/
```

This guide should help prevent and resolve webhook truncation issues in your WhatsApp integration.
