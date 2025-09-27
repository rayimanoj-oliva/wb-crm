# 🚀 Production Deployment Checklist

## ✅ Pre-Deployment Checklist

### 1. **Database Migration**
```bash
# Run this on your server
alembic upgrade head
```

### 2. **Environment Variables**
Make sure these are set on your server:
```bash
DATABASE_URL=your_production_database_url
WHATSAPP_ACCESS_TOKEN=your_whatsapp_token
WHATSAPP_PHONE_ID=your_phone_id
```

### 3. **Server Configuration**
- ✅ FastAPI server running
- ✅ Database connection working
- ✅ WhatsApp webhook configured
- ✅ CORS settings for your domain

## 📁 Files to Deploy

### **Backend Files (Already in your codebase):**
- ✅ `models/models.py` - Database schema
- ✅ `services/referrer_service.py` - Referrer tracking logic
- ✅ `controllers/referrer_controller.py` - API endpoints
- ✅ `controllers/web_socket.py` - Webhook integration
- ✅ `schemas/referrer_schema.py` - Data schemas
- ✅ `alembic/versions/add_referrer_tracking_table.py` - Migration

### **Frontend Files (Deploy these):**
- ✅ `production_referrer.html` - Production website
- ✅ Update your existing website with UTM parameters

## 🔧 Production Setup

### **1. Update Your Website**
Replace your current WhatsApp links with UTM-enhanced versions:

**Old Link:**
```
https://wa.link/zixq1n
```

**New Links:**
```
# Banjara Hills
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=banjara_hills&utm_content=hyderabad

# Jubilee Hills  
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=jubilee_hills&utm_content=hyderabad

# Gachibowli
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=gachibowli&utm_content=hyderabad

# Mumbai Bandra
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=mumbai_bandra&utm_content=mumbai

# Delhi Gurgaon
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=delhi_gurgaon&utm_content=delhi
```

### **2. Test Production Setup**
```bash
# Test API endpoints
curl -X GET "https://your-domain.com/referrer/" -H "accept: application/json"

# Test specific user
curl -X GET "https://your-domain.com/referrer/918309866900" -H "accept: application/json"
```

## 📊 Monitoring Production

### **1. Check Referrer Tracking**
```bash
# Monitor all activity
python monitor_referrer.py

# Check specific user
python monitor_referrer.py check 918309866900
```

### **2. Database Verification**
```sql
-- Check referrer tracking table
SELECT * FROM referrer_tracking ORDER BY created_at DESC LIMIT 10;

-- Check by center
SELECT center_name, location, COUNT(*) as visitors 
FROM referrer_tracking 
GROUP BY center_name, location;
```

## 🎯 Expected Results

### **When users click WhatsApp links:**
1. ✅ **Referrer tracking record** created automatically
2. ✅ **Center name and location** captured correctly
3. ✅ **UTM parameters** stored in database
4. ✅ **Appointment confirmations** include center details

### **Example appointment confirmation:**
> "✅ Thank you! Your preferred appointment is 2024-01-15 at 10:00 AM at Oliva Clinics Banjara Hills, Hyderabad. Our team will call and confirm shortly."

## 🔍 Troubleshooting

### **If referrer tracking is not working:**
1. Check webhook logs
2. Verify database connection
3. Test API endpoints
4. Check WhatsApp webhook configuration

### **Common Issues:**
- Database migration not run
- Environment variables not set
- CORS issues
- WhatsApp webhook not configured

## 📞 Support

If you need help with deployment:
1. Check server logs
2. Test API endpoints
3. Verify database connection
4. Check WhatsApp webhook status
