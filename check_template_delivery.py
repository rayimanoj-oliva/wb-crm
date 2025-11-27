"""
Check who received template messages from the results file.
Shows a clear breakdown of successful vs failed deliveries.
"""
import json
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

def check_delivery_status(results_file: str):
    """
    Analyze the results file and show who got templates and who didn't.
    """
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Results file not found: {results_file}")
        print("   Make sure you've run the bulk sender script first.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON file: {e}")
        sys.exit(1)
    
    total = results.get('total', 0)
    success = results.get('success', 0)
    failed = results.get('failed', 0)
    pending = results.get('pending', 0)
    rate_limited = results.get('rate_limited', 0)
    skipped = len([d for d in results.get('details', []) if d.get('status') == 'skipped'])
    
    # Calculate percentages
    success_rate = (success / total * 100) if total > 0 else 0
    failure_rate = (failed / total * 100) if total > 0 else 0
    pending_rate = (pending / total * 100) if total > 0 else 0
    
    print("=" * 70)
    print("📊 TEMPLATE DELIVERY STATUS REPORT")
    print("=" * 70)
    print()
    
    # Summary
    print("📋 SUMMARY:")
    print(f"   Total Recipients: {total}")
    print(f"   ✅ Received Template: {success} ({success_rate:.2f}%)")
    print(f"   ❌ Did NOT Receive Template: {failed} ({failure_rate:.2f}%)")
    print(f"   ⏸ Pending/In Queue: {pending} ({pending_rate:.2f}%)")
    if rate_limited > 0:
        print(f"   ⚠ Rate Limited: {rate_limited}")
    if skipped > 0:
        print(f"   ⏭ Skipped: {skipped}")
    print()
    
    # Answer the question
    print("=" * 70)
    if success == total and pending == 0:
        print("✅ YES - Everyone received the template message!")
    elif success > 0 and failed == 0 and pending > 0:
        print(f"⏸ PARTIAL - {success} received, {pending} still pending")
    elif success > 0:
        print(f"⚠ PARTIAL - {success} received, {failed} did NOT receive")
        print(f"   Success Rate: {success_rate:.2f}%")
    else:
        print("❌ NO - No one received the template message")
        print("   Check the Failed sheet for error details")
    print("=" * 70)
    print()
    
    # Breakdown by status
    print("📊 BREAKDOWN BY STATUS:")
    details = results.get('details', [])
    
    success_list = [d for d in details if d.get('status') == 'success']
    failed_list = [d for d in details if d.get('status') == 'failed']
    rate_limited_list = [d for d in details if d.get('status') == 'rate_limited']
    skipped_list = [d for d in details if d.get('status') == 'skipped']
    
    print(f"   ✅ Successful: {len(success_list)} recipients")
    print(f"   ❌ Failed: {len(failed_list)} recipients")
    if rate_limited_list:
        print(f"   ⚠ Rate Limited: {len(rate_limited_list)} recipients")
    if skipped_list:
        print(f"   ⏭ Skipped: {len(skipped_list)} recipients")
    print()
    
    # Show failed recipients if any
    if failed_list or rate_limited_list:
        print("❌ RECIPIENTS WHO DID NOT RECEIVE TEMPLATE:")
        print("-" * 70)
        for detail in failed_list + rate_limited_list:
            row = detail.get('row', 'N/A')
            phone = detail.get('phone_number', 'N/A')
            error = detail.get('error', 'Unknown error')
            status = detail.get('status', 'failed')
            print(f"   Row {row}: {phone} - {status.upper()}")
            if error and error != 'Unknown error':
                print(f"      Error: {error[:60]}...")
        print()
    
    # Timing information
    if results.get('start_time') and results.get('end_time'):
        duration = results.get('duration_seconds', 0)
        start_time = datetime.fromtimestamp(results.get('start_time'))
        end_time = datetime.fromtimestamp(results.get('end_time'))
        print("⏱ TIMING:")
        print(f"   Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   End: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Duration: {duration/60:.2f} minutes")
        print()
    
    # Recommendations
    print("💡 RECOMMENDATIONS:")
    if failed > 0:
        print("   1. Check the Excel report 'Failed' sheet for error details")
        print("   2. Review failed phone numbers - may need retry")
        if rate_limited > 0:
            print("   3. Some messages hit rate limits - consider slower sending")
    if pending > 0:
        print("   1. Some messages are still pending - script may need to complete")
    if success_rate >= 95:
        print("   ✅ Excellent success rate! Campaign performed well.")
    elif success_rate >= 80:
        print("   ⚠ Good success rate, but some messages failed. Review failures.")
    else:
        print("   ❌ Low success rate. Check errors and retry failed messages.")
    print()
    
    # Check if Excel report exists
    results_path = Path(results_file)
    excel_report = results_path.parent / f"{results_path.stem.replace('_results', '')}_statistics_report.xlsx"
    if excel_report.exists():
        print(f"📊 Detailed Excel report available: {excel_report.name}")
        print("   Open it to see complete breakdown by status")
    else:
        print("📊 Run the bulk sender to generate Excel statistics report")
    print()


def main():
    """Main function."""
    if len(sys.argv) < 2:
        # Default to recipients_results.json if it exists
        default_file = "recipients_results.json"
        if Path(default_file).exists():
            results_file = default_file
        else:
            print("Usage: python check_template_delivery.py <results_json_file>")
            print("\nExample:")
            print("  python check_template_delivery.py recipients_results.json")
            sys.exit(1)
    else:
        results_file = sys.argv[1]
    
    check_delivery_status(results_file)


if __name__ == "__main__":
    main()

