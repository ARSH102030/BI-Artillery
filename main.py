import os
import re
from auth import get_access_token
from api_client import FabricClient
from downloader import download_pbix, download_pbir
from logger import logger

def sanitize_filename(name):
    # Remove characters that are illegal in Windows filenames
    return re.sub(r'[\\/*?:"<>|]', "", name)

def run():
    logger.info("=========================================")
    logger.info("Starting up Interactive Power BI Report Downloader...")
    
    tenant_id = "organizations"
    base_download_dir = "./downloads"
    
    os.makedirs(base_download_dir, exist_ok=True)
    
    try:
        # 1. Interactive Authentication (No custom Client ID required)
        access_token = get_access_token(tenant_id)
        client = FabricClient(access_token)
        
        # 2. Fetch accessible workspaces
        logger.info("Fetching accessible workspaces...")
        all_workspaces = client.get_workspaces()
        
        if not all_workspaces:
            print("No workspaces found.")
            return

        print("\n" + "="*50)
        print("AVAILABLE WORKSPACES:")
        for idx, ws in enumerate(all_workspaces):
            print(f"  [{idx + 1}] {ws.get('displayName')}")
        print("="*50)
        
        ws_choice = input("\nEnter the number of the Workspace to explore: ").strip()
        if not ws_choice.isdigit() or not (1 <= int(ws_choice) <= len(all_workspaces)):
            print("Invalid workspace selection. Exiting.")
            return
            
        selected_ws = all_workspaces[int(ws_choice) - 1]
        ws_id = selected_ws.get("id")
        ws_name = selected_ws.get("displayName")
        
        print(f"\nFetching items in Workspace: {ws_name}...")
        all_items = client.get_items(ws_id)
        
        # Filter items to just Reports for downloading
        reports = [item for item in all_items if item.get("type") == "Report"]
        
        if not reports:
            print(f"No Reports found in {ws_name}.")
            return

        print("\n" + "="*50)
        print(f"REPORTS IN '{ws_name}':")
        for idx, report in enumerate(reports):
            print(f"  [{idx + 1}] {report.get('displayName')}")
        print("="*50)
        print("  [A] Download ALL Reports")
        
        rep_choice = input("\nEnter report numbers to download (comma-separated, e.g. '1,3,4') or 'A' for all: ").strip()
        
        selected_reports = []
        if rep_choice.upper() == 'A':
            selected_reports = reports
        else:
            try:
                indices = [int(x.strip()) - 1 for x in rep_choice.split(",") if x.strip().isdigit()]
                selected_reports = [reports[i] for i in indices if 0 <= i < len(reports)]
            except Exception as e:
                print("Invalid input. Exiting.")
                return

        if not selected_reports:
            print("No valid reports selected. Exiting.")
            return

        print(f"\nSelected {len(selected_reports)} report(s). Starting downloads...\n")
        
        ws_dir = os.path.join(base_download_dir, sanitize_filename(ws_name))
        os.makedirs(ws_dir, exist_ok=True)
            
        for report in selected_reports:
            report_name = report.get("displayName")
            report_id = report.get("id")
            
            safe_report_name = sanitize_filename(report_name)
            
            # Fetch Structural PBIR Definition
            logger.info(f"Initiating PBIR download for report: {report_name}")
            download_pbir(client, ws_id, report_id, safe_report_name, ws_dir)
            
            # Fetch binary PBIX File
            logger.info(f"Initiating PBIX download for report: {report_name}")
            download_pbix(client, ws_id, report_id, safe_report_name, ws_dir)
                
    except Exception as e:
        logger.error(f"Execution terminated due to an error: {e}", exc_info=True)
    
    logger.info("Power BI Report Downloader finished.")
    logger.info("=========================================")

if __name__ == "__main__":
    run()