#!/usr/bin/env python3
"""
Quick Razorpay Setup Script
Interactive script to help set up Razorpay configuration
"""

import os
import sys
from pathlib import Path

def create_env_file():
    """Create .env file with Razorpay configuration"""
    print("🔧 Creating .env file for Razorpay configuration")
    print("=" * 50)
    
    env_file = Path(".env")
    
    if env_file.exists():
        print("⚠️  .env file already exists!")
        response = input("Do you want to overwrite it? (y/N): ").lower()
        if response != 'y':
            print("Skipping .env file creation.")
            return
    
    print("\nPlease provide your Razorpay credentials:")
    print("(You can find these in your Razorpay Dashboard → Settings → API Keys)")
    print()
    
    # Get credentials from user
    key_id = input("Enter your Razorpay Key ID (rzp_test_... or rzp_live_...): ").strip()
    secret = input("Enter your Razorpay Secret: ").strip()
    webhook_secret = input("Enter your Webhook Secret (whsec_...): ").strip()
    
    # Validate inputs
    if not key_id.startswith('rzp_'):
        print("❌ Invalid Key ID format. Should start with 'rzp_test_' or 'rzp_live_'")
        return
    
    if not webhook_secret.startswith('whsec_'):
        print("❌ Invalid Webhook Secret format. Should start with 'whsec_'")
        return
    
    # Create .env content
    env_content = f"""# Razorpay Configuration
RAZORPAY_KEY_ID={key_id}
RAZORPAY_SECRET={secret}
RAZORPAY_BASE_URL=https://api.razorpay.com/v1

# Webhook Configuration
RAZORPAY_WEBHOOK_SECRET={webhook_secret}

# Optional: Proxy Configuration (if using fallback)
# RAZORPAY_USERNAME=your_username
# RAZORPAY_PASSWORD=your_password
# RAZORPAY_TOKEN_URL=https://payments.olivaclinic.com/api/token
# RAZORPAY_PAYMENT_URL=https://payments.olivaclinic.com/api/payment

# Optional: Shopify Configuration
# SHOPIFY_STORE=your-store
# SHOPIFY_API_KEY=your_api_key
# SHOPIFY_PASSWORD=your_password
"""
    
    # Write .env file
    try:
        with open(env_file, 'w') as f:
            f.write(env_content)
        print(f"✅ .env file created successfully!")
        print(f"📁 Location: {env_file.absolute()}")
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")

def load_env_file():
    """Load environment variables from .env file"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Environment variables loaded from .env file")
        return True
    except ImportError:
        print("⚠️  python-dotenv not installed. Install it with: pip install python-dotenv")
        return False
    except Exception as e:
        print(f"❌ Error loading .env file: {e}")
        return False

def test_configuration():
    """Test the configuration"""
    print("\n🧪 Testing Configuration")
    print("=" * 30)
    
    try:
        # Import and test Razorpay client
        from payment.razorpay_client import RazorpayClient
        
        client = RazorpayClient()
        print("✅ Razorpay client initialized successfully")
        
        # Test payment creation
        response = client.create_payment_link(
            amount=1.0,
            description="Test payment from setup script"
        )
        
        if "error" in response:
            print(f"❌ Payment test failed: {response['error']}")
            return False
        else:
            print(f"✅ Payment test successful!")
            print(f"   Payment ID: {response.get('id')}")
            return True
            
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def show_next_steps():
    """Show next steps for the user"""
    print("\n🚀 Next Steps")
    print("=" * 30)
    print("1. ✅ Razorpay configuration is set up")
    print("2. 🔧 Test your configuration:")
    print("   python check_razorpay_config.py")
    print("3. 🧪 Test payment creation:")
    print("   curl -X POST 'http://localhost:8000/payments/create' \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"amount\": 100, \"currency\": \"INR\"}'")
    print("4. 🔍 Check diagnostics:")
    print("   curl -X GET 'http://localhost:8000/payments/diagnostics'")
    print("5. 📚 Read the full guide:")
    print("   RAZORPAY_INTEGRATION_GUIDE.md")

def main():
    """Main setup function"""
    print("🚀 Razorpay Quick Setup")
    print("=" * 50)
    print("This script will help you set up Razorpay configuration.")
    print()
    
    # Check if .env file exists
    env_file = Path(".env")
    if not env_file.exists():
        print("📝 No .env file found. Let's create one!")
        create_env_file()
    else:
        print("📝 .env file found.")
        response = input("Do you want to update it? (y/N): ").lower()
        if response == 'y':
            create_env_file()
    
    # Load environment variables
    print("\n🔄 Loading environment variables...")
    if not load_env_file():
        print("❌ Failed to load environment variables")
        print("Please set them manually:")
        print("export RAZORPAY_KEY_ID='your_key_id'")
        print("export RAZORPAY_SECRET='your_secret'")
        print("export RAZORPAY_WEBHOOK_SECRET='your_webhook_secret'")
        return
    
    # Test configuration
    if test_configuration():
        print("\n🎉 Setup completed successfully!")
        show_next_steps()
    else:
        print("\n❌ Setup failed. Please check your credentials and try again.")
        print("\n📋 Troubleshooting:")
        print("1. Verify your Razorpay credentials in the dashboard")
        print("2. Make sure you're using the correct Key ID and Secret")
        print("3. Check if your Razorpay account is active")
        print("4. Run: python check_razorpay_config.py")

if __name__ == "__main__":
    main()
