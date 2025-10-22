# WhatsApp Flow Data Storage Troubleshooting Guide

## Issue: User-typed data not being stored from WhatsApp flows

### Problem Description
Users fill out WhatsApp flow forms (like address collection), but the data is not being saved to the database. The system shows "Address saved successfully!" but the data is not actually stored.

### Root Causes Analysis

#### 1. **Data Extraction Issues**
- Flow payload structure doesn't match expected format
- Field mapping is incorrect
- Data is being extracted but in wrong format

#### 2. **Database Transaction Issues**
- Database connection problems
- Transaction rollback due to validation errors
- Silent failures in address creation

#### 3. **Field Validation Failures**
- Required fields are missing or empty
- Data format validation failing
- Schema validation errors

#### 4. **Flow Configuration Issues**
- Flow token problems
- Incorrect flow field names
- Template variable substitution issues

### Debugging Steps

#### Step 1: Check Webhook Logs
```bash
# Look for recent webhook logs
ls -la webhook_logs/ | tail -10

# Check for flow-related logs
grep -r "flow_handler" webhook_logs/ | tail -20

# Check for address creation logs
grep -r "Address saved successfully" webhook_logs/
```

#### Step 2: Verify Data Extraction
Look for these debug messages in logs:
```
[flow_handler] DEBUG - Extracted address data: {...}
[flow_handler] DEBUG - Raw flow payload keys: [...]
[flow_handler] DEBUG - Raw flow payload values: {...}
[flow_debug] Flow payload keys: [...]
[flow_debug] Common fields found in payload: [...]
```

#### Step 3: Check Database
```sql
-- Check if addresses are being created
SELECT * FROM customer_addresses ORDER BY created_at DESC LIMIT 10;

-- Check for recent customers
SELECT * FROM customers ORDER BY created_at DESC LIMIT 10;

-- Check for any failed transactions
SELECT * FROM customer_addresses WHERE full_name = '' OR house_street = '';
```

### Enhanced Debugging Features Added

#### 1. **Comprehensive Logging**
- Raw flow payload logging
- Extracted data validation
- Field mapping analysis
- Database operation tracking

#### 2. **Error Detection**
- Missing field detection
- Empty value validation
- Template variable detection
- Database error handling

#### 3. **Data Validation**
- Required field checking
- Data format validation
- Schema compliance checking

### Common Issues and Solutions

#### Issue 1: "No data extracted from flow response"
**Symptoms:**
- Logs show empty address_data
- Flow payload has data but extraction fails

**Solutions:**
1. Check flow field names match the mapping
2. Verify flow token is valid
3. Check for template variable issues

#### Issue 2: "Missing required fields"
**Symptoms:**
- Some fields are empty
- Validation fails before saving

**Solutions:**
1. Check flow configuration
2. Verify field names in flow
3. Add fallback data extraction

#### Issue 3: "Address creation failed"
**Symptoms:**
- Database error in logs
- Exception during address creation

**Solutions:**
1. Check database connection
2. Verify schema compliance
3. Check for constraint violations

### Debug Commands

#### Check Recent Webhook Activity
```bash
# Find recent flow submissions
grep -r "nfm_reply" webhook_logs/ | tail -10

# Check for data extraction issues
grep -r "WARNING.*No data extracted" webhook_logs/

# Check for address creation
grep -r "Address saved successfully" webhook_logs/
```

#### Database Verification
```sql
-- Check recent address creation
SELECT 
    ca.id,
    ca.full_name,
    ca.house_street,
    ca.city,
    ca.pincode,
    ca.phone,
    ca.created_at,
    c.wa_id
FROM customer_addresses ca
JOIN customers c ON ca.customer_id = c.id
ORDER BY ca.created_at DESC
LIMIT 5;

-- Check for empty addresses
SELECT * FROM customer_addresses 
WHERE full_name = '' OR house_street = '' OR city = ''
ORDER BY created_at DESC;
```

### Testing the Fix

#### 1. **Send Test Flow**
- Trigger address collection flow
- Fill out the form completely
- Submit the form

#### 2. **Check Logs**
```bash
# Monitor logs in real-time
tail -f webhook_logs/webhook_*.json

# Check for debug messages
grep -r "flow_handler.*DEBUG" webhook_logs/ | tail -20
```

#### 3. **Verify Database**
```sql
-- Check if address was created
SELECT * FROM customer_addresses 
WHERE created_at > NOW() - INTERVAL '5 minutes'
ORDER BY created_at DESC;
```

### Prevention Measures

#### 1. **Enhanced Validation**
- Pre-save validation of all fields
- Better error messages for users
- Automatic retry mechanisms

#### 2. **Monitoring**
- Real-time logging of data extraction
- Database operation tracking
- Error rate monitoring

#### 3. **Fallback Mechanisms**
- Alternative data extraction methods
- User-friendly error messages
- Automatic form resend on failure

### Expected Log Output

#### Successful Flow Processing
```
[webhook_debug] NFM response_json length: 150
[webhook_debug] NFM parsed keys: ['name', 'phone', 'address', 'city', 'pincode']
[flow_debug] Flow payload keys: ['name', 'phone', 'address', 'city', 'pincode']
[flow_debug] Common fields found in payload: ['name', 'phone', 'address', 'city', 'pincode']
[flow_handler] DEBUG - Extracted address data: {'full_name': 'John Doe', 'phone_number': '9876543210', 'house_street': '123 Main St', 'city': 'Mumbai', 'pincode': '400001'}
[flow_handler] DEBUG - AddressCreate object created successfully
[flow_handler] DEBUG - Address saved successfully with ID: 123e4567-e89b-12d3-a456-426614174000
```

#### Failed Flow Processing
```
[flow_handler] WARNING - No data extracted from flow response!
[flow_handler] WARNING - This might indicate a flow configuration issue or data extraction problem
[webhook_debug] WARNING - Template variables detected in parsed data!
[flow_handler] ERROR - Missing required fields: ['full_name', 'phone_number']
```

### Next Steps

1. **Monitor the enhanced logging** to identify the exact issue
2. **Check database** for any created addresses
3. **Verify flow configuration** matches the expected field names
4. **Test with a simple flow** to isolate the problem
5. **Check for template variable issues** in the flow response

The enhanced debugging should now provide clear visibility into where the data storage process is failing.
