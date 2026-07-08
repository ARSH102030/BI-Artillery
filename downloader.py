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
        size_kb = round(len(content) / 1024, 1)
        logger.info(f"Downloaded PBIX: {file_path}")
        return True, f"PBIX binary exported successfully ({size_kb} KB) \u2192 saved as '{report_name}.pbix'."
    except Exception as e:
        err = str(e)
        if "401" in err or "403" in err:
            reason = "Access denied when exporting PBIX. Your account lacks 'Build' or 'Member' permission on this report/workspace."
        elif "404" in err:
            reason = "Report not found. It may have been deleted or is a Semantic Model without a downloadable PBIX."
        elif "PowerBINotAuthorizedException" in err or "is not supported" in err.lower():
            reason = "PBIX export is not supported for this item (e.g. reports built on live-connected or DirectQuery models hosted elsewhere)."
        else:
            reason = f"PBIX export failed: {err}"
        logger.error(f"Failed to download PBIX for report '{report_name}': {e}")
        return False, reason

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
        
        file_count = 0
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
                file_count += 1
                    
        fmt = "TMDL" if item_type == "SemanticModel" else "PBIR"
        logger.info(f"Downloaded {item_type} structure into: {pbir_dir}")
        return True, f"{fmt} definition extracted successfully ({file_count} file(s)) into folder '{os.path.basename(pbir_dir)}'."
    except Exception as e:
        err = str(e)
        if "401" in err or "403" in err:
            reason = f"Access denied reading the {item_type} definition. You need 'Member' or 'Admin' rights on this workspace."
        elif "empty definition" in err.lower():
            reason = err
        elif "No definition found" in err:
            reason = "Fabric returned no definition. This item type does not expose a downloadable structure."
        else:
            reason = f"Structure ({item_type}) export failed: {err}"
        logger.error(f"Failed to download PBIR for {item_type} '{report_name}': {e}")
        return False, reason