import os
import base64
from api_client import FabricClient
from logger import logger

def download_pbix(client: FabricClient, workspace_id, report_id, report_name, save_dir):
    try:
        content = client.get_dataset_export(workspace_id, report_id)
        file_path = os.path.join(save_dir, f"{report_name}.pbix")
        with open(file_path, 'wb') as f:
            f.write(content)
        logger.info(f"Downloaded PBIX: {file_path}")
        return True, ""
    except Exception as e:
        logger.error(f"Failed to download PBIX for report '{report_name}': {e}")
        return False, f"PBIX failure: {str(e)}"

def download_pbir(client: FabricClient, workspace_id, item_id, report_name, save_dir, item_type="Report"):
    try:
        req_format = "TMDL" if item_type == "SemanticModel" else None
        definition = client.get_item_definition(workspace_id, item_id, format=req_format)
        print(f"DEBUG: Retrieved definition for {report_name} ({item_type}): {definition}")
        if not definition:
            logger.warning(f"No definition found for {item_type} '{report_name}'.")
            return False, "No definition found in Fabric API response."

        # PBIR definition consists of base64 decoded files
        # It could be named "definition" or "parts" inside depending on where we unpacked it
        parts = definition.get("parts", [])
        if not parts and "definition" in definition:
            parts = definition["definition"].get("parts", [])
            
        if not parts:
            raise Exception(f"Microsoft Fabric returned an empty definition for this {item_type}. This usually occurs when the Semantic Model relies on features not yet supported by PBIR or TMDL export formats.")

        # We create a directory for the formatted item
        suffix = ".Report" if item_type == "Report" else ".Dataset"
        pbir_dir = os.path.join(save_dir, f"{report_name}{suffix}")
        os.makedirs(pbir_dir, exist_ok=True)
        
        for part in parts:
            part_path = part.get("path")
            payload = part.get("payload", "")
            payload_type = part.get("payloadType", "")
            
            if payload_type == "InlineBase64":
                file_content = base64.b64decode(payload)
                
                full_part_path = os.path.join(pbir_dir, part_path)
                os.makedirs(os.path.dirname(full_part_path), exist_ok=True)
                
                with open(full_part_path, 'wb') as f:
                    f.write(file_content)
                    
        logger.info(f"Downloaded {item_type} structure into: {pbir_dir}")
        return True, ""
    except Exception as e:
        logger.error(f"Failed to download PBIR for {item_type} '{report_name}': {e}")
        return False, f"PBIR structure failure: {str(e)}"