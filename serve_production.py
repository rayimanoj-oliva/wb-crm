#!/usr/bin/env python3
"""
Serve production_referrer.html locally for testing
"""
import http.server
import socketserver
import os
import webbrowser
from pathlib import Path

def serve_production():
    """Serve the production referrer page locally"""
    print("🚀 Starting Production Referrer Page Server")
    print("=" * 50)
    
    # Change to the directory containing the HTML file
    os.chdir(Path(__file__).parent)
    
    # Set up the server
    PORT = 8080
    Handler = http.server.SimpleHTTPRequestHandler
    
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print(f"🌐 Server running at: http://localhost:{PORT}")
            print(f"📱 Production page: http://localhost:{PORT}/production_referrer.html")
            print(f"🧪 Test page: http://localhost:{PORT}/test_online_referrer.html")
            print("\n📋 Available pages:")
            print("   • production_referrer.html - Production website")
            print("   • test_online_referrer.html - Testing website")
            print("\n🛑 Press Ctrl+C to stop the server")
            
            # Open the production page in browser
            webbrowser.open(f"http://localhost:{PORT}/production_referrer.html")
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    serve_production()
