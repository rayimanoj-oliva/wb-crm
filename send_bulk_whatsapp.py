"""
Bulk WhatsApp Message Sender
Reads phone numbers and button URLs from Excel file and sends WhatsApp template messages.
"""
import pandas as pd
import requests
import json
import sys
import os
import argparse
import time
from pathlib import Path
from sqlalchemy.orm import Session
from database.db import SessionLocal
from services.whatsapp_service import get_latest_token

# Meta WhatsApp API Configuration (defaults)
DEFAULT_API_URL = "https://graph.facebook.com/v22.0/367633743092037/messages"
DEFAULT_TEMPLATE_NAME = "pune_clinic_offer"
DEFAULT_TEMPLATE_LANGUAGE = "en_US"
DEFAULT_IMAGE_ID = "1223826332973821"  # Header image ID from your request

def send_whatsapp_message(phone_number: str, button_url_param: str, token: str, 
                         api_url: str, template_name: str, template_language: str, image_id: str,
                         max_retries: int = 3, retry_delay: int = 5) -> dict:
    """
    Send WhatsApp template message to a phone number.
    
    Args:
        phone_number: Recipient phone number (e.g., "918309866859")
        button_url_param: Button URL parameter (e.g., "3WBCRqn")
        token: WhatsApp access token
        api_url: Meta Graph API URL
        template_name: WhatsApp template name
        template_language: Template language code
        image_id: Header image ID
    
    Returns:
        dict: Response from Meta API
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Validate and clean phone number
    # Remove any non-digit characters except leading +
    clean_phone = ''.join(c for c in phone_number if c.isdigit() or c == '+')
    if clean_phone.startswith('+'):
        clean_phone = clean_phone[1:]
    
    # Validate phone number length (should be 10-15 digits typically)
    if len(clean_phone) < 10 or len(clean_phone) > 15:
        return {
            "success": False,
            "phone_number": phone_number,
            "error": f"Invalid phone number format: {phone_number} (cleaned: {clean_phone}, length: {len(clean_phone)})",
            "status_code": None
        }
    
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_language},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "image",
                            "image": {
                                "id": str(image_id).strip()
                            }
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "1",
                    "parameters": [
                        {
                            "type": "text",
                            "text": str(button_url_param).strip()
                        }
                    ]
                }
            ]
        }
    }
    
    # Retry logic for rate limiting and temporary errors
    for attempt in range(max_retries):
        try:
            # Debug: Log payload for first failed attempt (only for 400 errors)
            if attempt == 0:
                import json as json_module
                debug_payload = json_module.dumps(payload, indent=2)
                # Only log if we suspect it's a 400 error (first attempt)
                pass  # Commented out to avoid spam, uncomment for debugging
            
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            
            # Check for rate limiting (429) or server errors (5xx)
            if response.status_code == 429:
                # Rate limited - wait and retry
                wait_time = retry_delay * (attempt + 1)  # Exponential backoff
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        "success": False,
                        "phone_number": phone_number,
                        "error": "Rate limited - max retries exceeded",
                        "status_code": 429,
                        "response": response.json() if response.text else {}
                    }
            elif response.status_code >= 500:
                # Server error - retry
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    response.raise_for_status()
            
            # Check response status
            if response.status_code != 200:
                # Get detailed error from response
                try:
                    response_data = response.json()
                    error_info = response_data.get("error", {})
                    error_msg = error_info.get("message", f"HTTP {response.status_code} Error")
                    error_code = error_info.get("code", response.status_code)
                    error_type = error_info.get("type", "Unknown")
                    error_subcode = error_info.get("error_subcode", None)
                    error_user_msg = error_info.get("error_user_msg", "")
                    
                    detailed_error = f"API Error ({error_code})"
                    if error_subcode:
                        detailed_error += f" [Subcode: {error_subcode}]"
                    detailed_error += f": {error_msg}"
                    if error_user_msg:
                        detailed_error += f" - {error_user_msg}"
                    
                    return {
                        "success": False,
                        "phone_number": phone_number,
                        "error": detailed_error,
                        "status_code": response.status_code,
                        "error_code": error_code,
                        "error_type": error_type,
                        "error_subcode": error_subcode,
                        "response": response_data
                    }
                except:
                    # If can't parse JSON, return raw response
                    return {
                        "success": False,
                        "phone_number": phone_number,
                        "error": f"HTTP {response.status_code}: {response.text[:200]}",
                        "status_code": response.status_code,
                        "response": {"raw": response.text}
                    }
            
            # Check for errors in response even if status is 200
            response_data = response.json()
            if "error" in response_data:
                error_info = response_data.get("error", {})
                error_msg = error_info.get("message", "Unknown API error")
                error_code = error_info.get("code", "N/A")
                error_type = error_info.get("type", "N/A")
                
                return {
                    "success": False,
                    "phone_number": phone_number,
                    "error": f"API Error ({error_code}): {error_msg}",
                    "status_code": response.status_code,
                    "error_code": error_code,
                    "error_type": error_type,
                    "response": response_data
                }
            
            response.raise_for_status()
            return {
                "success": True,
                "phone_number": phone_number,
                "response": response_data,
                "attempts": attempt + 1
            }
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return {
                "success": False,
                "phone_number": phone_number,
                "error": "Request timeout - max retries exceeded",
                "attempts": max_retries
            }
        except requests.exceptions.RequestException as e:
            # Check if it's a rate limit error in the response
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                
                # Try to get detailed error from response
                try:
                    error_data = e.response.json()
                    if "error" in error_data:
                        error_info = error_data.get("error", {})
                        error_msg = error_info.get("message", str(e))
                        error_code = error_info.get("code", "N/A")
                        error_type = error_info.get("type", "N/A")
                        detailed_error = f"API Error ({error_code}): {error_msg}"
                    else:
                        detailed_error = str(e)
                        error_code = None
                        error_type = None
                except:
                    detailed_error = str(e)
                    error_data = {}
                    error_code = None
                    error_type = None
                
                if status_code == 429:
                    wait_time = retry_delay * (attempt + 1)
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                
                return {
                    "success": False,
                    "phone_number": phone_number,
                    "error": detailed_error,
                    "status_code": status_code,
                    "error_code": error_code,
                    "error_type": error_type,
                    "response": error_data
                }
            return {
                "success": False,
                "phone_number": phone_number,
                "error": str(e),
                "response": getattr(e.response, 'json', lambda: {})() if hasattr(e, 'response') else {}
            }
    
    return {
        "success": False,
        "phone_number": phone_number,
        "error": "Max retries exceeded",
        "attempts": max_retries
    }


def process_excel_file(excel_path: str, db: Session, api_url: str, template_name: str, 
                       template_language: str, image_id: str, delay_between_messages: float = 0.1,
                       batch_size: int = 100, batch_delay: int = 60) -> dict:
    """
    Read Excel file and send WhatsApp messages to all recipients.
    
    Expected Excel/CSV columns:
    - phone_number: Phone number (e.g., "918309866859")
    - button_url or button_params: Button URL parameter (e.g., "3WBCRqn")
    
    Args:
        excel_path: Path to Excel file (.xlsx or .xls)
        db: Database session
    
    Returns:
        dict: Summary of results
    """
    # Get WhatsApp token from database
    token_obj = get_latest_token(db)
    if not token_obj:
        raise Exception("WhatsApp token not found in database. Please add a token first.")
    
    token = token_obj.token
    print(f"✓ Token retrieved from database")
    
    # Read Excel or CSV file
    try:
        file_ext = Path(excel_path).suffix.lower()
        df = None
        
        # Try Excel format first if extension suggests it
        if file_ext in ['.xlsx', '.xls']:
            try:
                df = pd.read_excel(excel_path, engine='openpyxl')
                print(f"✓ Excel file loaded: {len(df)} rows found")
            except Exception as excel_error:
                # If Excel fails, try CSV (file might be misnamed)
                print(f"⚠ Excel read failed, trying CSV format...")
                try:
                    df = pd.read_csv(excel_path, sep='\t')
                    print(f"✓ CSV file (tab-separated) loaded: {len(df)} rows found")
                except Exception:
                    try:
                        df = pd.read_csv(excel_path, sep=',')
                        print(f"✓ CSV file (comma-separated) loaded: {len(df)} rows found")
                    except Exception:
                        try:
                            df = pd.read_csv(excel_path, sep=';')
                            print(f"✓ CSV file (semicolon-separated) loaded: {len(df)} rows found")
                        except Exception:
                            raise Exception(f"Could not read as Excel or CSV. Excel error: {excel_error}")
        elif file_ext == '.csv':
            # Try different CSV separators
            try:
                df = pd.read_csv(excel_path, sep=',')
                print(f"✓ CSV file (comma-separated) loaded: {len(df)} rows found")
            except Exception:
                try:
                    df = pd.read_csv(excel_path, sep='\t')
                    print(f"✓ CSV file (tab-separated) loaded: {len(df)} rows found")
                except Exception:
                    df = pd.read_csv(excel_path, sep=';')
                    print(f"✓ CSV file (semicolon-separated) loaded: {len(df)} rows found")
        else:
            # Try to detect format automatically - try Excel first, then CSV
            try:
                df = pd.read_excel(excel_path, engine='openpyxl')
                print(f"✓ Excel file loaded: {len(df)} rows found")
            except Exception:
                # If Excel fails, try CSV with different separators
                try:
                    df = pd.read_csv(excel_path, sep='\t')
                    print(f"✓ CSV file (tab-separated) loaded: {len(df)} rows found")
                except Exception:
                    try:
                        df = pd.read_csv(excel_path, sep=',')
                        print(f"✓ CSV file (comma-separated) loaded: {len(df)} rows found")
                    except Exception:
                        df = pd.read_csv(excel_path, sep=';')
                        print(f"✓ CSV file (semicolon-separated) loaded: {len(df)} rows found")
        
        if df is None or df.empty:
            raise Exception("File is empty or could not be read")
            
    except Exception as e:
        raise Exception(f"Failed to read file: {e}. Make sure it's a valid Excel (.xlsx) or CSV file.")
    
    # Normalize column names (strip whitespace, handle case variations)
    df.columns = df.columns.str.strip()
    
    # Check for required columns (accept both button_url and button_params)
    if "phone_number" not in df.columns:
        raise Exception(f"Missing required column 'phone_number' in file. Found columns: {', '.join(df.columns.tolist())}")
    
    # Accept either button_url or button_params
    button_col = None
    if "button_url" in df.columns:
        button_col = "button_url"
    elif "button_params" in df.columns:
        button_col = "button_params"
    else:
        raise Exception(f"Missing required column 'button_url' or 'button_params' in file. Found columns: {', '.join(df.columns.tolist())}")
    
    # Rename button_params to button_url for consistency
    if button_col == "button_params":
        df = df.rename(columns={"button_params": "button_url"})
        print(f"✓ Note: Found 'button_params' column, using it as 'button_url'")
    
    # Process each row
    results = {
        "total": len(df),
        "success": 0,
        "failed": 0,
        "rate_limited": 0,
        "details": [],
        "start_time": time.time()
    }
    
    print(f"\nStarting to send messages to {results['total']} recipients...")
    print(f"Configuration:")
    print(f"  - Delay between messages: {delay_between_messages}s")
    print(f"  - Batch size: {batch_size} messages")
    print(f"  - Batch delay: {batch_delay}s")
    estimated_time = (results['total'] * delay_between_messages) + ((results['total'] // batch_size) * batch_delay)
    print(f"  - Estimated time: ~{estimated_time/60:.1f} minutes")
    print("-" * 60)
    
    # Save progress periodically
    progress_file = Path(excel_path).stem + "_progress.json"
    last_save_time = time.time()
    
    batch_count = 0
    for index, row in df.iterrows():
        phone_number = str(row["phone_number"]).strip()
        button_url = str(row.get("button_url", "")).strip()
        
        # Skip empty rows
        if not phone_number or phone_number.lower() in ["nan", "none", ""]:
            print(f"⚠ Row {index + 1}: Skipping empty phone number")
            results["failed"] += 1
            results["details"].append({
                "row": index + 1,
                "phone_number": phone_number,
                "status": "skipped",
                "reason": "Empty phone number"
            })
            continue
        
        # Remove any non-digit characters except leading +
        phone_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')
        if phone_number.startswith('+'):
            phone_number = phone_number[1:]
        
        if not button_url or button_url.lower() in ["nan", "none", ""]:
            print(f"⚠ Row {index + 1}: Skipping {phone_number} - missing button_url")
            results["failed"] += 1
            results["details"].append({
                "row": index + 1,
                "phone_number": phone_number,
                "status": "skipped",
                "reason": "Empty button_url"
            })
            continue
        
        # Send message
        current_num = index + 1
        print(f"📤 Row {current_num}/{results['total']}: Sending to {phone_number}...", end=" ", flush=True)
        result = send_whatsapp_message(phone_number, button_url, token, api_url, 
                                      template_name, template_language, image_id)
        
        if result["success"]:
            print("✓ Success")
            results["success"] += 1
            results["details"].append({
                "row": current_num,
                "phone_number": phone_number,
                "status": "success",
                "message_id": result["response"].get("messages", [{}])[0].get("id", "N/A"),
                "attempts": result.get("attempts", 1)
            })
        else:
            error_msg = result.get('error', 'Unknown error')
            status_code = result.get('status_code')
            error_code = result.get('error_code')
            error_type = result.get('error_type')
            
            # Show more detailed error for 400 errors
            if status_code == 400:
                # Extract key error details
                error_details = error_msg
                if error_code:
                    error_details = f"[{error_code}] {error_msg}"
                
                # Always show full error for first 5 failures to help debug
                if results["failed"] < 5:
                    print(f"✗ Failed: {error_details}")
                    print(f"   Phone: {phone_number}")
                    if error_type:
                        print(f"   Error type: {error_type}")
                    error_subcode = result.get('error_subcode')
                    if error_subcode:
                        print(f"   Error subcode: {error_subcode}")
                    response_data = result.get("response", {})
                    if "error" in response_data:
                        error_info = response_data.get("error", {})
                        if "error_user_title" in error_info:
                            print(f"   User message: {error_info['error_user_title']}")
                        if "error_user_msg" in error_info:
                            print(f"   Details: {error_info['error_user_msg']}")
                        # Show fbtrace_id for debugging
                        if "fbtrace_id" in error_info:
                            print(f"   Trace ID: {error_info['fbtrace_id']}")
                else:
                    print(f"✗ Failed: {error_details[:60]}")  # Truncate for subsequent errors
            # Check if rate limited
            elif status_code == 429 or "rate limit" in error_msg.lower():
                print(f"⚠ Rate Limited")
                results["rate_limited"] += 1
                results["failed"] += 1
                results["details"].append({
                    "row": current_num,
                    "phone_number": phone_number,
                    "status": "rate_limited",
                    "error": error_msg,
                    "error_code": error_code,
                    "error_type": error_type,
                    "response": result.get("response", {})
                })
            else:
                print(f"✗ Failed: {error_msg[:80]}")
                results["failed"] += 1
                results["details"].append({
                    "row": current_num,
                    "phone_number": phone_number,
                    "status": "failed",
                    "error": error_msg,
                    "error_code": error_code,
                    "error_type": error_type,
                    "response": result.get("response", {})
                })
        
        # Delay between messages to avoid rate limiting
        if delay_between_messages > 0 and current_num < results['total']:
            time.sleep(delay_between_messages)
        
        # Save progress every 50 messages or every 30 seconds
        current_time = time.time()
        if current_num % 50 == 0 or (current_time - last_save_time) > 30:
            try:
                results["end_time"] = current_time
                results["duration_seconds"] = current_time - results["start_time"]
                results["pending"] = results["total"] - results["success"] - results["failed"]
                with open(progress_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                last_save_time = current_time
            except Exception:
                pass  # Don't fail if progress save fails
        
        # Show progress every 10 messages
        if current_num % 10 == 0:
            elapsed = time.time() - results["start_time"]
            progress_pct = (current_num / results['total']) * 100
            remaining = results['total'] - current_num
            estimated_remaining = (remaining * delay_between_messages) + ((remaining // batch_size) * batch_delay)
            print(f"   Progress: {current_num}/{results['total']} ({progress_pct:.1f}%) | "
                  f"Success: {results['success']} | Failed: {results['failed']} | "
                  f"ETA: ~{estimated_remaining/60:.1f} min")
        
        # Batch delay - pause after every N messages
        if batch_size > 0 and current_num % batch_size == 0 and current_num < results['total']:
            batch_count += 1
            elapsed = time.time() - results["start_time"]
            progress_pct = (current_num / results['total']) * 100
            print(f"\n⏸ Batch {batch_count} completed ({current_num}/{results['total']} messages - {progress_pct:.1f}%)")
            print(f"   Progress: {results['success']} success, {results['failed']} failed")
            print(f"   Elapsed time: {elapsed/60:.1f} minutes")
            remaining = results['total'] - current_num
            estimated_remaining = (remaining * delay_between_messages) + ((remaining // batch_size) * batch_delay)
            print(f"   Estimated remaining: ~{estimated_remaining/60:.1f} minutes")
            print(f"   Pausing for {batch_delay} seconds to avoid rate limits...")
            time.sleep(batch_delay)
            print("   Resuming...\n")
    
    results["end_time"] = time.time()
    results["duration_seconds"] = results["end_time"] - results["start_time"]
    
    # Calculate pending (not yet sent - this would be messages that are queued but not processed)
    # In this script, pending = total - success - failed (messages not yet attempted)
    results["pending"] = results["total"] - results["success"] - results["failed"]
    
    # Final progress save
    try:
        progress_file = Path(excel_path).stem + "_progress.json"
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    
    return results


def open_excel_file(file_path: str):
    """
    Automatically open Excel file in the default application.
    Works on Windows, Mac, and Linux.
    """
    import platform
    import subprocess
    
    file_path = os.path.abspath(file_path)
    
    # Verify file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Excel file not found: {file_path}")
    
    try:
        if platform.system() == 'Windows':
            # Windows: use start command (most reliable)
            os.startfile(file_path)
            # Also try subprocess as backup
            time.sleep(0.5)  # Small delay to ensure file is ready
        elif platform.system() == 'Darwin':  # macOS
            # macOS: use open command
            subprocess.run(['open', file_path], check=True)
        else:  # Linux and other Unix-like systems
            # Linux: try xdg-open
            subprocess.run(['xdg-open', file_path], check=True)
    except Exception as e:
        # If os.startfile fails, try subprocess
        if platform.system() == 'Windows':
            try:
                subprocess.Popen(['start', '', file_path], shell=True)
            except Exception:
                # Last resort: try with excel.exe directly
                try:
                    subprocess.Popen([file_path], shell=True)
                except Exception as e2:
                    raise Exception(f"Could not open Excel file: {e}, {e2}")
        else:
            raise


def generate_statistics_report(results: dict, original_file_path: str) -> str:
    """
    Generate a comprehensive statistics Excel report.
    
    Returns:
        str: Path to the generated Excel file
    """
    from datetime import datetime
    
    output_file = Path(original_file_path).stem + "_statistics_report.xlsx"
    
    try:
        # Prepare summary statistics
        total = results['total']
        success = results['success']
        failed = results['failed']
        pending = results.get('pending', 0)
        rate_limited = results.get('rate_limited', 0)
        skipped = len([d for d in results.get('details', []) if d.get('status') == 'skipped'])
        
        processed = success + failed
        success_rate = (success / processed * 100) if processed > 0 else 0
        failure_rate = (failed / processed * 100) if processed > 0 else 0
        pending_rate = (pending / total * 100) if total > 0 else 0
        
        duration_min = results.get('duration_seconds', 0) / 60
        start_time = datetime.fromtimestamp(results.get('start_time', time.time()))
        end_time = datetime.fromtimestamp(results.get('end_time', time.time()))
        
        # Summary statistics
        summary_data = [{
            "Statistic": "Total Recipients",
            "Count": total,
            "Percentage": "100.00%"
        }, {
            "Statistic": "Successful",
            "Count": success,
            "Percentage": f"{(success/total*100):.2f}%" if total > 0 else "0.00%"
        }, {
            "Statistic": "Failed",
            "Count": failed,
            "Percentage": f"{(failed/total*100):.2f}%" if total > 0 else "0.00%"
        }, {
            "Statistic": "Pending/In Queue",
            "Count": pending,
            "Percentage": f"{pending_rate:.2f}%"
        }, {
            "Statistic": "Rate Limited",
            "Count": rate_limited,
            "Percentage": f"{(rate_limited/total*100):.2f}%" if total > 0 else "0.00%"
        }, {
            "Statistic": "Skipped",
            "Count": skipped,
            "Percentage": f"{(skipped/total*100):.2f}%" if total > 0 else "0.00%"
        }, {
            "Statistic": "Success Rate (of processed)",
            "Count": f"{success_rate:.2f}%",
            "Percentage": f"{failure_rate:.2f}% failure rate"
        }, {
            "Statistic": "Duration (minutes)",
            "Count": f"{duration_min:.2f}",
            "Percentage": "-"
        }, {
            "Statistic": "Start Time",
            "Count": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Percentage": "-"
        }, {
            "Statistic": "End Time",
            "Count": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Percentage": "-"
        }]
        
        # Separate details by status
        success_details = []
        failed_details = []
        pending_details = []
        
        for detail in results.get('details', []):
            status = detail.get('status', '')
            row_data = {
                "Row Number": detail.get('row', 'N/A'),
                "Phone Number": detail.get('phone_number', 'N/A'),
                "Status": status.title(),
            }
            
            if status == 'success':
                row_data["Message ID"] = detail.get('message_id', 'N/A')
                row_data["Attempts"] = detail.get('attempts', 1)
                success_details.append(row_data)
            elif status in ['failed', 'rate_limited']:
                row_data["Error"] = detail.get('error', 'N/A')
                row_data["Status Code"] = detail.get('status_code', 'N/A')
                if status == 'rate_limited':
                    row_data["Status"] = "Rate Limited"
                failed_details.append(row_data)
            elif status == 'skipped':
                row_data["Reason"] = detail.get('reason', 'N/A')
                pending_details.append(row_data)
        
        # Create Excel file with multiple sheets
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # Summary Statistics sheet
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Statistics Summary', index=False)
            
            # Successful messages sheet
            if success_details:
                pd.DataFrame(success_details).to_excel(writer, sheet_name='Successful', index=False)
            else:
                pd.DataFrame([{"Message": "No successful messages"}]).to_excel(writer, sheet_name='Successful', index=False)
            
            # Failed messages sheet
            if failed_details:
                pd.DataFrame(failed_details).to_excel(writer, sheet_name='Failed', index=False)
            else:
                pd.DataFrame([{"Message": "No failed messages"}]).to_excel(writer, sheet_name='Failed', index=False)
            
            # Pending/Skipped sheet
            if pending_details:
                pd.DataFrame(pending_details).to_excel(writer, sheet_name='Pending_Skipped', index=False)
            else:
                pd.DataFrame([{"Message": "No pending or skipped messages"}]).to_excel(writer, sheet_name='Pending_Skipped', index=False)
            
            # All details sheet
            all_details = []
            for detail in results.get('details', []):
                all_details.append({
                    "Row": detail.get('row', 'N/A'),
                    "Phone Number": detail.get('phone_number', 'N/A'),
                    "Status": detail.get('status', 'N/A').title(),
                    "Message ID": detail.get('message_id', ''),
                    "Error": detail.get('error', ''),
                    "Reason": detail.get('reason', ''),
                    "Attempts": detail.get('attempts', 1),
                    "Status Code": detail.get('status_code', '')
                })
            pd.DataFrame(all_details).to_excel(writer, sheet_name='All Details', index=False)
        
        return output_file
    except Exception as e:
        print(f"⚠ Warning: Could not generate statistics report: {e}")
        return ""


def main():
    """Main function to run the bulk WhatsApp sender."""
    parser = argparse.ArgumentParser(
        description="Send bulk WhatsApp messages from Excel file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
File must have the following columns (Excel .xlsx/.xls or CSV):
  - phone_number: Recipient phone number (e.g., 918309866859)
  - button_url or button_params: Button URL parameter (e.g., 3WBCRqn)

Example:
  python send_bulk_whatsapp.py recipients.xlsx
  python send_bulk_whatsapp.py recipients.csv
  python send_bulk_whatsapp.py recipients.xlsx --template-name my_template --image-id 123456
        """
    )
    parser.add_argument("excel_file", help="Path to Excel file with phone numbers and button URLs")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, 
                       help=f"Meta Graph API URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--template-name", default=DEFAULT_TEMPLATE_NAME,
                       help=f"WhatsApp template name (default: {DEFAULT_TEMPLATE_NAME})")
    parser.add_argument("--template-language", default=DEFAULT_TEMPLATE_LANGUAGE,
                       help=f"Template language code (default: {DEFAULT_TEMPLATE_LANGUAGE})")
    parser.add_argument("--image-id", default=DEFAULT_IMAGE_ID,
                       help=f"Header image ID (default: {DEFAULT_IMAGE_ID})")
    parser.add_argument("--delay", type=float, default=0.1,
                       help="Delay in seconds between messages (default: 0.1)")
    parser.add_argument("--batch-size", type=int, default=100,
                       help="Number of messages per batch before pause (default: 100)")
    parser.add_argument("--batch-delay", type=int, default=60,
                       help="Delay in seconds between batches (default: 60)")
    parser.add_argument("--no-auto-open", action="store_true",
                       help="Don't automatically open Excel report after generation")
    
    args = parser.parse_args()
    
    # Validate file exists
    if not os.path.exists(args.excel_file):
        print(f"Error: File not found: {args.excel_file}")
        sys.exit(1)
    
    # Initialize database session
    db = SessionLocal()
    try:
        # Process Excel file and send messages
        try:
            results = process_excel_file(
                args.excel_file, 
                db, 
                args.api_url,
                args.template_name,
                args.template_language,
                args.image_id,
                args.delay,
                args.batch_size,
                args.batch_delay
            )
        except KeyboardInterrupt:
            print("\n\n⚠ Script interrupted by user (Ctrl+C)")
            print("Saving current progress...")
            # Try to load progress file if it exists
            progress_file = Path(args.excel_file).stem + "_progress.json"
            if os.path.exists(progress_file):
                with open(progress_file, "r", encoding="utf-8") as f:
                    results = json.load(f)
                print(f"✓ Loaded progress from: {progress_file}")
            else:
                print("⚠ No progress file found. Generating report from current state...")
                # Create minimal results from what we have
                results = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "pending": 0,
                    "rate_limited": 0,
                    "details": [],
                    "start_time": time.time(),
                    "end_time": time.time(),
                    "duration_seconds": 0
                }
            raise  # Re-raise to handle in outer except
        
        # Print summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total recipients: {results['total']}")
        print(f"✓ Successful: {results['success']}")
        print(f"✗ Failed: {results['failed']}")
        print(f"⏸ Pending/Queue: {results.get('pending', 0)}")
        if results.get('rate_limited', 0) > 0:
            print(f"⚠ Rate Limited: {results['rate_limited']}")
        duration_min = results.get('duration_seconds', 0) / 60
        print(f"⏱ Total time: {duration_min:.1f} minutes")
        
        # Calculate success rate
        processed = results['success'] + results['failed']
        if processed > 0:
            success_rate = (results['success'] / processed) * 100
            print(f"📊 Success Rate: {success_rate:.2f}%")
        
        # Clear answer to "Did everyone get the template?"
        print("\n" + "=" * 60)
        total = results['total']
        success = results['success']
        failed = results['failed']
        pending = results.get('pending', 0)
        
        if success == total and pending == 0:
            print("✅ YES - Everyone received the template message!")
        elif success > 0 and failed == 0 and pending > 0:
            print(f"⏸ PARTIAL - {success} received, {pending} still pending")
        elif success > 0:
            print(f"⚠ PARTIAL - {success} received template, {failed} did NOT receive")
        else:
            print("❌ NO - No one received the template message")
            print("   Check the Failed sheet in Excel report for details")
        print("=" * 60)
        
        # Save detailed results to JSON file
        output_file = Path(args.excel_file).stem + "_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nDetailed results saved to: {output_file}")
        
        # Always generate statistics report, even if interrupted
        print("\n" + "=" * 60)
        print("📊 GENERATING STATISTICS REPORT...")
        print("=" * 60)
        excel_report_file = generate_statistics_report(results, args.excel_file)
        if excel_report_file:
            full_path = os.path.abspath(excel_report_file)
            print(f"✅ Statistics report saved to: {excel_report_file}")
            print(f"   📁 Full path: {full_path}")
            
            # Automatically open the Excel file (unless disabled)
            if not args.no_auto_open:
                print(f"\n📂 Opening Excel report automatically...")
                try:
                    # Small delay to ensure file is fully written and closed
                    time.sleep(2)
                    
                    # Verify file exists and is accessible
                    if not os.path.exists(excel_report_file):
                        raise FileNotFoundError(f"Excel file not found: {excel_report_file}")
                    
                    # Open the file
                    open_excel_file(excel_report_file)
                    
                    print(f"✅ Excel report opened successfully!")
                    print(f"   📊 The Excel file should now be open in Excel/your spreadsheet app")
                    print(f"   📋 Check the 'Statistics Summary' sheet for overview")
                    print(f"   📈 Review 'Successful', 'Failed', and 'Pending_Skipped' sheets for details")
                    
                except Exception as e:
                    print(f"\n⚠ Could not auto-open Excel file automatically: {e}")
                    print(f"\n📂 Please open manually:")
                    print(f"   1. Open Windows Explorer")
                    print(f"   2. Navigate to: {os.path.dirname(full_path)}")
                    print(f"   3. Double-click: {os.path.basename(excel_report_file)}")
                    print(f"\n   Or copy this path and paste in File Explorer:")
                    print(f"   {full_path}")
        else:
            print("⚠ Could not generate Excel report. JSON results are still available.")
        
        if results["failed"] > 0:
            print("\n⚠ Some messages failed. Check the results file for details.")
            if results.get("pending", 0) > 0:
                print(f"⚠ {results['pending']} messages are still pending/not sent.")
        else:
            if results.get("pending", 0) == 0:
                print("\n✓ All messages sent successfully!")
            else:
                print(f"\n⚠ Script completed but {results['pending']} messages are still pending.")
            
    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("SCRIPT INTERRUPTED - GENERATING REPORT FROM PROGRESS...")
        print("=" * 60)
        # Try to generate report from saved progress
        progress_file = Path(args.excel_file).stem + "_progress.json"
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    results = json.load(f)
                excel_report_file = generate_statistics_report(results, args.excel_file)
                if excel_report_file:
                    print(f"✓ Statistics report generated from progress: {excel_report_file}")
                    if not args.no_auto_open:
                        try:
                            open_excel_file(excel_report_file)
                        except Exception:
                            pass
            except Exception as e:
                print(f"⚠ Could not generate report from progress: {e}")
        print("\n⚠ Script was interrupted. Check progress file for current status.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

