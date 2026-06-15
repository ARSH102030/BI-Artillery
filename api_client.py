import requests
import time
from logger import logger

class FabricClient:
    def __init__(self, access_token):
        self.access_token = access_token
        self.fabric_base_url = "https://api.fabric.microsoft.com/v1"
        self.pbi_base_url = "https://api.powerbi.com/v1.0/myorg"

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _get(self, url):
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_workspaces(self):
        url = f"{self.fabric_base_url}/workspaces"
        return self._get(url).get("value", [])

    def get_items(self, workspace_id):
        url = f"{self.fabric_base_url}/workspaces/{workspace_id}/items"
        return self._get(url).get("value", [])

    def get_reports(self, workspace_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/reports"
        return self._get(url).get("value", [])

    def get_datasets(self, workspace_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/datasets"
        return self._get(url).get("value", [])

    def get_dataset_export(self, workspace_id, report_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/reports/{report_id}/Export"
        response = requests.get(url, headers=self.headers, stream=True)
        response.raise_for_status()
        return response.content

    def get_item_definition(self, workspace_id, item_id, format=None):
        url = f"{self.fabric_base_url}/workspaces/{workspace_id}/items/{item_id}/getDefinition"
        
        payload = {}
        if format:
            payload["format"] = format
            
        response = requests.post(url, headers=self.headers, json=payload if payload else None)
        if response.status_code == 202:
            # Long-running operation handling
            operation_id = response.headers.get("Location") or response.headers.get("Operation-Location")
            if not operation_id:
                raise Exception("No operation location returned for long running task.")
            
            # Polling
            while True:
                time.sleep(2)
                op_response = requests.get(operation_id, headers=self.headers)
                op_response.raise_for_status()
                op_json = op_response.json()
                
                # Check Fabric API status
                status = op_json.get("status", "")
                if status == "Succeeded":
                    # Get the result from {operation_id}/result
                    result_url = f"{operation_id}/result"
                    res_resp = requests.get(result_url, headers=self.headers)
                    res_resp.raise_for_status()
                    res_json = res_resp.json()
                    return res_json.get("definition", res_json)
                elif status == "Failed":
                    logger.error(f"getDefinition operation failed: {op_json.get('error')}")
                    raise Exception("getDefinition Failed")
                elif status in ["NotStarted", "Running"]:
                    continue
        else:
            response.raise_for_status()
            return response.json().get("definition", {})

    def create_folder(self, workspace_id, folder_name, parent_folder_id=None):
        url = f"{self.fabric_base_url}/workspaces/{workspace_id}/folders"
        payload = {"displayName": folder_name}
        if parent_folder_id:
            payload["parentFolderId"] = parent_folder_id
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def get_folders(self, workspace_id):
        url = f"{self.fabric_base_url}/workspaces/{workspace_id}/folders"
        return self._get(url).get("value", [])

    def get_import(self, workspace_id, import_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/imports/{import_id}"
        return self._get(url)

    def upload_pbix(self, workspace_id, file_path, report_name, name_conflict="CreateOrOverwrite"):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/imports?datasetDisplayName={report_name}&nameConflict={name_conflict}"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}"
            # Let requests set Content-Type for multipart/form-data automatically
        }
        
        with open(file_path, "rb") as f:
            files = {
                "value": (report_name + ".pbix", f, "application/octet-stream")
            }
            response = requests.post(url, headers=headers, files=files)
            response.raise_for_status()
            
            import_info = response.json()
            import_id = import_info.get("id")

            # Polling for import completion
            while True:
                time.sleep(2)
                status_res = self.get_import(workspace_id, import_id)
                state = status_res.get("importState")
                if state == "Succeeded":
                    return status_res
                elif state == "Failed":
                    raise Exception(f"Import Failed: {status_res}")
                elif state in ["Publishing", "Importing"]:
                    continue

    def rebind_report(self, workspace_id, report_id, dataset_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/reports/{report_id}/Rebind"
        payload = {"datasetId": dataset_id}
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response

    def update_report_content(self, workspace_id, target_report_id, source_report_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/reports/{target_report_id}/UpdateReportContent"
        payload = {
            "sourceReport": {
                "sourceReportId": source_report_id,
                "sourceWorkspaceId": workspace_id
            },
            "sourceType": "ExistingReport"
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response

    def delete_report(self, workspace_id, report_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/reports/{report_id}"
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
        return response
