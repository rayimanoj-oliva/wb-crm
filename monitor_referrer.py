#!/usr/bin/env python3
"""
Referrer tracking monitoring dashboard
"""
import requests
import json
from datetime import datetime, timedelta
import time

BASE_URL = "http://127.0.0.1:8000"

def monitor_referrer_data():
    """Monitor referrer tracking data in real-time"""
    print("📊 Referrer Tracking Monitor")
    print("=" * 40)
    
    try:
        # Get all referrer records
        response = requests.get(
            f"{BASE_URL}/referrer/",
            headers={"accept": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if not data:
                print("📭 No referrer tracking records found")
                return
            
            print(f"📈 Total Records: {len(data)}")
            print("\n📋 Recent Referrer Activity:")
            print("-" * 50)
            
            # Group by center
            centers = {}
            for record in data:
                center = record['center_name']
                if center not in centers:
                    centers[center] = []
                centers[center].append(record)
            
            # Display by center
            for center, records in centers.items():
                print(f"\n🏥 {center}")
                print(f"   📊 Total visitors: {len(records)}")
                
                # Show recent records
                recent_records = sorted(records, key=lambda x: x['created_at'], reverse=True)[:3]
                for record in recent_records:
                    created_time = datetime.fromisoformat(record['created_at'].replace('Z', '+00:00'))
                    time_ago = datetime.now() - created_time.replace(tzinfo=None)
                    
                    if time_ago.days > 0:
                        time_str = f"{time_ago.days}d ago"
                    elif time_ago.seconds > 3600:
                        time_str = f"{time_ago.seconds // 3600}h ago"
                    elif time_ago.seconds > 60:
                        time_str = f"{time_ago.seconds // 60}m ago"
                    else:
                        time_str = "just now"
                    
                    print(f"   📱 {record['wa_id']} - {time_str}")
                    print(f"      🏷️  UTM: {record['utm_campaign']}")
                    print(f"      🌐 Source: {record['referrer_url'] or 'Direct'}")
            
            # Summary statistics
            print(f"\n📊 Summary Statistics:")
            print(f"   🏥 Unique Centers: {len(centers)}")
            print(f"   📱 Total Visitors: {len(data)}")
            
            # UTM campaign breakdown
            utm_campaigns = {}
            for record in data:
                campaign = record.get('utm_campaign', 'unknown')
                utm_campaigns[campaign] = utm_campaigns.get(campaign, 0) + 1
            
            print(f"\n🎯 UTM Campaign Breakdown:")
            for campaign, count in sorted(utm_campaigns.items(), key=lambda x: x[1], reverse=True):
                print(f"   {campaign}: {count} visitors")
                
        else:
            print(f"❌ Failed to get referrer data: {response.text}")
            
    except Exception as e:
        print(f"❌ Error monitoring referrer data: {e}")

def check_specific_user(wa_id):
    """Check referrer data for a specific user"""
    print(f"\n🔍 Checking referrer data for {wa_id}...")
    
    try:
        response = requests.get(
            f"{BASE_URL}/referrer/{wa_id}",
            headers={"accept": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Referrer tracking found!")
            print(f"   🏥 Center: {data['center_name']}")
            print(f"   📍 Location: {data['location']}")
            print(f"   🏷️  UTM Campaign: {data['utm_campaign']}")
            print(f"   🌐 Referrer URL: {data['referrer_url']}")
            print(f"   📅 Created: {data['created_at']}")
        elif response.status_code == 404:
            print("❌ No referrer tracking found for this user")
        else:
            print(f"❌ Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error checking user: {e}")

def real_time_monitor():
    """Real-time monitoring with auto-refresh"""
    print("🔄 Real-time Referrer Monitor")
    print("=" * 40)
    print("Press Ctrl+C to stop monitoring")
    
    try:
        while True:
            print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            monitor_referrer_data()
            print("\n" + "="*50)
            time.sleep(30)  # Refresh every 30 seconds
            
    except KeyboardInterrupt:
        print("\n\n🛑 Monitoring stopped")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "monitor":
            real_time_monitor()
        elif sys.argv[1] == "check":
            if len(sys.argv) > 2:
                check_specific_user(sys.argv[2])
            else:
                print("Usage: python monitor_referrer.py check <wa_id>")
        else:
            print("Usage: python monitor_referrer.py [monitor|check <wa_id>]")
    else:
        monitor_referrer_data()
