# 🚀 Production Deployment Guide

## 📁 Files to Deploy

### **1. HTML Files (Deploy to your web server):**
- ✅ `production_referrer.html` - Main production website
- ✅ `test_online_referrer.html` - Testing website (optional)

### **2. Backend Files (Already in your codebase):**
- ✅ All referrer tracking code is already integrated
- ✅ Database migration ready
- ✅ API endpoints working

## 🌐 Deployment Methods

### **Method 1: Direct File Upload**

#### **Using FTP/SFTP:**
```bash
# Upload to your web server
scp production_referrer.html user@your-server.com:/var/www/html/
# or
ftp your-server.com
put production_referrer.html
```

#### **Using cPanel File Manager:**
1. Login to cPanel
2. Go to File Manager
3. Navigate to `public_html` folder
4. Upload `production_referrer.html`
5. Rename to `index.html` (if you want it as homepage)

### **Method 2: Git Deployment**

#### **If you have a Git repository:**
```bash
# Add the file to your repository
git add production_referrer.html
git commit -m "Add production referrer tracking page"
git push origin main

# On your server, pull the changes
git pull origin main
```

### **Method 3: Cloud Deployment**

#### **GitHub Pages:**
1. Create a new repository
2. Upload `production_referrer.html`
3. Enable GitHub Pages
4. Your site will be live at `https://username.github.io/repository-name`

#### **Netlify:**
1. Drag and drop `production_referrer.html` to Netlify
2. Your site will be live instantly
3. Custom domain can be added

#### **Vercel:**
1. Connect your GitHub repository
2. Deploy automatically
3. Custom domain available

## 🔧 Server Configuration

### **1. Web Server Setup (Apache/Nginx)**

#### **Apache (.htaccess):**
```apache
RewriteEngine On
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^(.*)$ production_referrer.html [QSA,L]
```

#### **Nginx:**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /var/www/html;
    index production_referrer.html;
    
    location / {
        try_files $uri $uri/ /production_referrer.html;
    }
}
```

### **2. Domain Configuration**

#### **Update your domain:**
- Point your domain to your server
- Update DNS records
- Configure SSL certificate (HTTPS)

## 📱 WhatsApp Links Configuration

### **Current Links (Ready to use):**
```html
<!-- Banjara Hills -->
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=banjara_hills&utm_content=hyderabad

<!-- Jubilee Hills -->
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=jubilee_hills&utm_content=hyderabad

<!-- Gachibowli -->
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=gachibowli&utm_content=hyderabad

<!-- Mumbai Bandra -->
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=mumbai_bandra&utm_content=mumbai

<!-- Delhi Gurgaon -->
https://wa.link/zixq1n?utm_source=olivaclinics&utm_medium=website&utm_campaign=delhi_gurgaon&utm_content=delhi
```

## 🧪 Testing After Deployment

### **1. Test the Website:**
```bash
# Check if the page loads
curl -I https://your-domain.com/production_referrer.html

# Test WhatsApp links
# Click each WhatsApp button and verify UTM parameters
```

### **2. Test Referrer Tracking:**
```bash
# Check API endpoints
curl -X GET "https://your-domain.com/referrer/" -H "accept: application/json"

# Monitor referrer data
python monitor_referrer.py
```

### **3. Verify Database:**
```sql
-- Check referrer tracking table
SELECT * FROM referrer_tracking ORDER BY created_at DESC LIMIT 10;
```

## 📊 Expected Results

### **When users visit your website:**
1. ✅ **Website loads** with all center locations
2. ✅ **WhatsApp buttons** work with UTM parameters
3. ✅ **Referrer tracking** captures center information
4. ✅ **Appointment confirmations** include center details

### **Example user flow:**
1. User visits your website
2. Clicks "WhatsApp Banjara Hills" button
3. WhatsApp opens with UTM parameters
4. User sends message: "Hi, I want to book an appointment"
5. System captures: "Oliva Clinics Banjara Hills, Hyderabad"
6. Appointment confirmation includes center information

## 🔍 Troubleshooting

### **Common Issues:**
- **Page not loading**: Check file permissions and web server configuration
- **WhatsApp links not working**: Verify UTM parameters are correct
- **Referrer tracking not working**: Check API endpoints and database connection
- **CORS issues**: Configure web server for cross-origin requests

### **Debug Commands:**
```bash
# Check server status
systemctl status apache2  # or nginx
systemctl status your-fastapi-service

# Check logs
tail -f /var/log/apache2/error.log
tail -f /var/log/nginx/error.log

# Test API endpoints
curl -X GET "https://your-domain.com/referrer/"
```

## 📞 Support

If you need help with deployment:
1. Check server logs
2. Verify file permissions
3. Test API endpoints
4. Check database connection
5. Verify WhatsApp webhook configuration
