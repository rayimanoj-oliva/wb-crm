"""
Quick script to check if bulk WhatsApp sender is running and show status.
"""
import os
import json
from pathlib import Path
from datetime import datetime

def check_script_status():
    """Check if the script is running and show current status."""
    print("=" * 70)
    print("🔍 CHECKING SCRIPT STATUS")
    print("=" * 70)
    print()
    
    # Check for progress file
    progress_files = list(Path(".").glob("*_progress.json"))
    if progress_files:
        latest_progress = max(progress_files, key=lambda p: p.stat().st_mtime)
        print(f"📁 Found progress file: {latest_progress.name}")
        print(f"   Last updated: {datetime.fromtimestamp(latest_progress.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            with open(latest_progress, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            
            total = progress.get('total', 0)
            success = progress.get('success', 0)
            failed = progress.get('failed', 0)
            pending = progress.get('pending', 0)
            
            if total > 0:
                completed = success + failed
                progress_pct = (completed / total) * 100
                
                print(f"\n📊 CURRENT STATUS:")
                print(f"   Total Recipients: {total}")
                print(f"   Completed: {completed} ({progress_pct:.2f}%)")
                print(f"   ✅ Successful: {success}")
                print(f"   ❌ Failed: {failed}")
                print(f"   ⏸ Pending: {pending}")
                print(f"   Remaining: {total - completed}")
                
                if progress.get('start_time'):
                    elapsed = progress.get('duration_seconds', 0) / 60
                    print(f"\n⏱ TIMING:")
                    print(f"   Elapsed: {elapsed:.2f} minutes")
                    if completed > 0:
                        avg_time_per_msg = elapsed / completed
                        remaining = total - completed
                        estimated_remaining = (avg_time_per_msg * remaining) / 60
                        print(f"   Estimated remaining: ~{estimated_remaining:.2f} minutes")
                
                print(f"\n✅ Script appears to be RUNNING or was recently running")
            else:
                print("   ⚠ Progress file exists but has no data")
        except Exception as e:
            print(f"   ⚠ Could not read progress file: {e}")
    else:
        print("📁 No progress file found")
    
    # Check for results file
    results_files = list(Path(".").glob("*_results.json"))
    if results_files:
        latest_results = max(results_files, key=lambda p: p.stat().st_mtime)
        print(f"\n📁 Found results file: {latest_results.name}")
        print(f"   Last updated: {datetime.fromtimestamp(latest_results.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            with open(latest_results, 'r', encoding='utf-8') as f:
                results = json.load(f)
            
            total = results.get('total', 0)
            success = results.get('success', 0)
            failed = results.get('failed', 0)
            
            if total > 0:
                if success + failed == total:
                    print(f"\n✅ Script appears to be COMPLETED")
                    print(f"   Total: {total}, Success: {success}, Failed: {failed}")
                else:
                    print(f"\n⏸ Script may have been interrupted")
                    print(f"   Total: {total}, Success: {success}, Failed: {failed}")
        except Exception as e:
            print(f"   ⚠ Could not read results file: {e}")
    
    # Check for Excel report
    report_files = list(Path(".").glob("*_statistics_report.xlsx"))
    if report_files:
        latest_report = max(report_files, key=lambda p: p.stat().st_mtime)
        print(f"\n📊 Found Excel report: {latest_report.name}")
        print(f"   Last updated: {datetime.fromtimestamp(latest_report.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   ✅ Report is available - you can open it to see details")
    
    # Check for running Python processes
    try:
        import psutil
        python_procs = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                if 'python' in proc.info['name'].lower():
                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    if 'send_bulk_whatsapp' in cmdline:
                        python_procs.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if python_procs:
            print(f"\n🔄 RUNNING PROCESSES:")
            for proc in python_procs:
                runtime = (psutil.boot_time() - proc.info['create_time']) / 60
                print(f"   PID {proc.info['pid']}: Running for ~{runtime:.1f} minutes")
            print(f"   ✅ Script appears to be RUNNING")
        else:
            print(f"\n🔄 No running Python processes found with 'send_bulk_whatsapp'")
            print(f"   Script may not be running or already completed")
    except ImportError:
        print(f"\n⚠ psutil not available - cannot check running processes")
    except Exception as e:
        print(f"\n⚠ Could not check processes: {e}")
    
    print()
    print("=" * 70)
    print("💡 TIP: Check the terminal window where you ran the script")
    print("   It will show real-time progress if it's running")
    print("=" * 70)


if __name__ == "__main__":
    check_script_status()

