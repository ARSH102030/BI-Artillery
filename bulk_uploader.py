import os
import re
from auth import get_access_token
from api_client import FabricClient
from logger import logger

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def get_or_create_folder(client, workspace_id, folder_name, parent_folder_id=None, existing_folders=None):
    if existing_folders is None:
        existing_folders = client.get_folders(workspace_id)
        
    for f in existing_folders:
        if f.get("displayName") == folder_name and f.get("parentFolderId") == parent_folder_id:
            return f.get("id"), existing_folders
            
    # Not found, create it
    logger.info(f"Creating folder '{folder_name}' in workspace...")
    new_folder = client.create_folder(workspace_id, folder_name, parent_folder_id)
    new_folder_id = new_folder.get("id")
    existing_folders.append({"id": new_folder_id, "displayName": folder_name, "parentFolderId": parent_folder_id})
    
    return new_folder_id, existing_folders

def run():
    logger.info("=========================================")
    logger.info("Starting up Interactive Power BI Bulk Uploader...")
    
    tenant_id = "a3c75d30-dfe5-4bd3-9fae-5e9fcc0d0997"
    
    try:
        # 1. Interactive Authentication
        access_token = get_access_token(tenant_id)
        client = FabricClient(access_token)
        
        # 2. Fetch accessible workspaces
        logger.info("Fetching accessible workspaces...")
        all_workspaces = client.get_workspaces()
        
        if not all_workspaces:
            print("No workspaces found.")
            return

        print("\n" + "="*50)
        print("VIEW ALL WORKSPACES & FOLDERS:")
        for idx, ws in enumerate(all_workspaces):
            ws_id = ws.get('id')
            ws_name = ws.get('displayName')
            print(f"\n[{idx + 1}] Workspace: {ws_name}")
            
            try:
                folders = client.get_folders(ws_id)
                if not folders:
                    print("      (No folders found)")
                else:
                    def print_tree(parent_id, indent=1):
                        for f in folders:
                            if f.get("parentFolderId") == parent_id:
                                prefix = "    " + "  " * indent
                                print(f"{prefix}[-] {f.get('displayName')}")
                                print_tree(f.get("id"), indent + 1)
                    print_tree(None, 1)
            except Exception as e:
                print(f"      (Error loading folders: {e})")

        print("="*50)
        
        ws_choice = input("\nEnter the number of the Workspace to upload to: ").strip()
        if not ws_choice.isdigit() or not (1 <= int(ws_choice) <= len(all_workspaces)):
            print("Invalid workspace selection. Exiting.")
            return
            
        selected_ws = all_workspaces[int(ws_choice) - 1]
        ws_id = selected_ws.get("id")
        ws_name = selected_ws.get("displayName")
        
        print(f"\nSelected Workspace: {ws_name}")

        target_dataset_name = input("\nEnter the name of the Target Dataset to rebind all reports to: ").strip()

        print("\nFetching existing datasets to find the target dataset...")
        datasets = client.get_datasets(ws_id)
        target_dataset_id = None
        for ds in datasets:
            if ds.get("name") == target_dataset_name:
                target_dataset_id = ds.get("id")
                break
        
        if not target_dataset_id:
            print(f"Dataset '{target_dataset_name}' not found in the workspace. Exiting.")
            return
        
        print(f"Found target Dataset ID: {target_dataset_id}")

        # 4. Prompt for local directory
        local_dir = input("\nEnter the absolute path of the local folder to upload: ").strip()
        
        if not os.path.exists(local_dir) or not os.path.isdir(local_dir):
            print("Invalid directory path. Exiting.")
            return

        print("\nStarting upload process...")
        existing_folders = client.get_folders(ws_id)
        
        # Recursively walk the local directory
        for root, dirs, files in os.walk(local_dir):
            # Calculate the relative path from the base directory
            rel_path = os.path.relpath(root, local_dir)
            
            parent_id = None
            
            # Resolve/Create nested folders in Power BI
            if rel_path != ".":
                path_parts = rel_path.split(os.sep)
                current_parent_id = None
                for part in path_parts:
                    current_parent_id, existing_folders = get_or_create_folder(
                        client, ws_id, part, current_parent_id, existing_folders
                    )
                parent_id = current_parent_id

            # Upload PBIX files in this directory
            for f in files:
                if f.lower().endswith(".pbix"):
                    file_path = os.path.join(root, f)
                    report_name = f[:-5] # remove .pbix extension
                    temp_report_name = f"temp_{report_name}"
                    
                    logger.info(f"Uploading temporary PBIX '{temp_report_name}' to workspace '{ws_name}'...")
                    try:
                        # 1. Upload as a temporary report
                        import_res = client.upload_pbix(ws_id, file_path, temp_report_name)
                        
                        # Extract the newly created temp report ID
                        imported_reports = import_res.get("reports", [])
                        if not imported_reports:
                            logger.error(f"No reports found in import response for {f}")
                            continue
                            
                        temp_report_id = imported_reports[0].get("id")
                        logger.info(f"Imported temp report ID: {temp_report_id}")
                        
                        # 2. Rebind the temp report to the new target dataset
                        logger.info(f"Rebinding temp report to dataset '{target_dataset_name}'...")
                        client.rebind_report(ws_id, temp_report_id, target_dataset_id)
                        
                        # 3. Find the original report ID to replace
                        existing_reports = client.get_reports(ws_id)
                        original_report_id = None
                        for r in existing_reports:
                            if r.get("name") == report_name:
                                original_report_id = r.get("id")
                                break
                                
                        if original_report_id:
                            # 4. Update existing report content from temp report
                            logger.info(f"Overwriting original report '{report_name}' content...")
                            client.update_report_content(ws_id, original_report_id, temp_report_id)
                            logger.info(f"Successfully updated: {f} (ID preserved)")
                        else:
                            logger.warning(f"Original report '{report_name}' not found. Cannot update content. (Temp remains)")
                            
                        # 5. Delete the temporary report
                        logger.info(f"Cleaning up temporary report '{temp_report_name}'...")
                        client.delete_report(ws_id, temp_report_id)
                        logger.info("Cleanup complete.")
                        
                    except Exception as e:
                        logger.error(f"Failed to process {f}. Error: {e}")

    except Exception as e:
        logger.error(f"Execution terminated due to an error: {e}", exc_info=True)
    
    logger.info("Power BI Bulk Uploader finished.")
    logger.info("=========================================")

if __name__ == "__main__":
    run()