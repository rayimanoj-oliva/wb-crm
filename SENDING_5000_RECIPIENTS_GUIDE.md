# 📱 Guide: Sending to 5000 Recipients

## ✅ Yes, You Can Send to 5000 People!

The script has been **enhanced with rate limiting and batch processing** to safely handle large volumes.

## ⚠️ Important: Meta API Rate Limits

Meta's WhatsApp API has rate limits:
- **New accounts**: ~1,000 conversations per 24 hours
- **Established accounts**: Up to 1,000 messages per second (with proper setup)
- **Template messages**: Subject to conversation limits

**For 5000 recipients, you need to:**
1. ✅ Use delays between messages
2. ✅ Process in batches with pauses
3. ✅ Handle rate limit errors gracefully
4. ✅ Allow sufficient time (several hours)

## 🚀 Recommended Settings for 5000 Recipients

### Option 1: Conservative (Recommended for First Time)
```powershell
python send_bulk_whatsapp.py recipients.xlsx `
    --delay 0.2 `
    --batch-size 50 `
    --batch-delay 120
```

**Time Estimate:** ~4-5 hours
- 0.2s delay between messages
- Pause 2 minutes after every 50 messages
- Very safe, avoids rate limits

### Option 2: Balanced (Good Balance)
```powershell
python send_bulk_whatsapp.py recipients.xlsx `
    --delay 0.1 `
    --batch-size 100 `
    --batch-delay 60
```

**Time Estimate:** ~2-3 hours
- 0.1s delay between messages
- Pause 1 minute after every 100 messages
- Good balance of speed and safety

### Option 3: Faster (If You Have High Limits)
```powershell
python send_bulk_whatsapp.py recipients.xlsx `
    --delay 0.05 `
    --batch-size 200 `
    --batch-delay 30
```

**Time Estimate:** ~1-2 hours
- 0.05s delay between messages
- Pause 30 seconds after every 200 messages
- Faster but monitor for rate limits

## 📋 Step-by-Step Process

### Step 1: Prepare Your Excel File
Ensure your file has 5000 rows with:
- `phone_number` column
- `button_url` or `button_params` column

### Step 2: Test with Small Batch First
**Always test with 10-20 recipients first!**

```powershell
# Create a test file with first 20 rows
python send_bulk_whatsapp.py test_recipients.xlsx --delay 0.1
```

### Step 3: Run Full Campaign
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run with recommended settings
python send_bulk_whatsapp.py recipients.xlsx `
    --delay 0.1 `
    --batch-size 100 `
    --batch-delay 60
```

### Step 4: Monitor Progress
The script will show:
- Real-time progress for each message
- Batch completion updates
- Rate limit warnings
- Final summary

## 🔧 New Features Added

### 1. **Rate Limit Handling**
- Automatically retries on rate limit errors (429)
- Exponential backoff for retries
- Tracks rate-limited messages separately

### 2. **Batch Processing**
- Processes messages in batches
- Automatic pauses between batches
- Prevents overwhelming the API

### 3. **Delays Between Messages**
- Configurable delay (default: 0.1s)
- Prevents hitting rate limits too quickly
- Adjustable based on your account limits

### 4. **Better Error Handling**
- Retries on temporary failures
- Distinguishes rate limits from other errors
- Saves detailed error information

### 5. **Progress Tracking**
- Shows elapsed time
- Displays batch progress
- Estimates completion time

## 📊 Example Output for Large Campaign

```
Starting to send messages to 5000 recipients...
Configuration:
  - Delay between messages: 0.1s
  - Batch size: 100 messages
  - Batch delay: 60s
  - Estimated time: ~90.0 minutes
------------------------------------------------------------
📤 Row 1/5000: Sending to 916304742913... ✓ Success
📤 Row 2/5000: Sending to 918309866859... ✓ Success
...

⏸ Batch 1 completed (100 messages sent)
   Progress: 98 success, 2 failed
   Elapsed time: 12.5 minutes
   Pausing for 60 seconds to avoid rate limits...
   Resuming...

============================================================
SUMMARY
============================================================
Total recipients: 5000
✓ Successful: 4850
✗ Failed: 150
⚠ Rate Limited: 12
⏱ Total time: 95.3 minutes
```

## ⚙️ Command-Line Options

```powershell
python send_bulk_whatsapp.py recipients.xlsx [OPTIONS]

Options:
  --delay DELAY              Delay in seconds between messages (default: 0.1)
  --batch-size SIZE          Messages per batch before pause (default: 100)
  --batch-delay SECONDS      Delay in seconds between batches (default: 60)
  --template-name NAME       Template name (default: pune_clinic_offer)
  --image-id ID              Header image ID
  --api-url URL              Meta Graph API URL
```

## 🎯 Best Practices

### 1. **Start Small**
- Test with 10-20 recipients first
- Verify messages are received correctly
- Check for any errors

### 2. **Monitor Rate Limits**
- Watch for rate limit warnings
- If you see many rate limits, increase delays
- Adjust batch size and delays accordingly

### 3. **Run During Off-Peak Hours**
- Meta's systems may be less loaded
- Better success rates
- Fewer rate limit issues

### 4. **Keep Script Running**
- Don't close the terminal
- Let it complete naturally
- Results are saved automatically

### 5. **Check Results File**
- Review `recipients_results.json` after completion
- Identify failed messages
- Retry failed ones if needed

## 🔄 Retrying Failed Messages

If some messages fail, you can:

1. **Extract failed phone numbers:**
```python
import json
with open('recipients_results.json') as f:
    results = json.load(f)
failed = [r for r in results['details'] if r['status'] == 'failed']
# Create new Excel with only failed numbers
```

2. **Run again with just failed numbers:**
```powershell
python send_bulk_whatsapp.py failed_recipients.xlsx --delay 0.2
```

## ⚠️ Troubleshooting

### Too Many Rate Limits?
**Solution:** Increase delays
```powershell
python send_bulk_whatsapp.py recipients.xlsx --delay 0.3 --batch-delay 180
```

### Script Taking Too Long?
**Solution:** Reduce delays (if your account allows)
```powershell
python send_bulk_whatsapp.py recipients.xlsx --delay 0.05 --batch-delay 30
```

### Connection Errors?
**Solution:** Check internet, increase retry delays
- Script automatically retries
- Check your network connection
- Verify API token is valid

### Some Messages Not Received?
**Solution:** Check results file
- Review `recipients_results.json`
- Check for specific error messages
- Verify phone numbers are correct format

## 📈 Time Estimates

| Recipients | Delay | Batch Size | Batch Delay | Estimated Time |
|------------|-------|------------|-------------|----------------|
| 5000 | 0.1s | 100 | 60s | ~2-3 hours |
| 5000 | 0.2s | 50 | 120s | ~4-5 hours |
| 5000 | 0.05s | 200 | 30s | ~1-2 hours |

## ✅ Checklist Before Sending 5000

- [ ] Tested with 10-20 recipients first
- [ ] Verified messages are received correctly
- [ ] Excel file has all 5000 rows
- [ ] Phone numbers are in correct format
- [ ] WhatsApp token is valid and not expired
- [ ] Chosen appropriate delay settings
- [ ] Have time to let script run (2-5 hours)
- [ ] Terminal/computer won't sleep during run

## 🎉 Success Tips

1. **Run overnight** - Let it complete while you sleep
2. **Use screen/tmux** - Keep session alive if SSH
3. **Monitor first batch** - Check if settings are good
4. **Save results** - JSON file has all details
5. **Be patient** - Large campaigns take time

---

**Remember:** It's better to go slower and succeed than to go fast and hit rate limits! 🚀

