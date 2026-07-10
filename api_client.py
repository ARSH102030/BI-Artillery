import requests
import time
from logger import logger

# (connect timeout, read timeout) in seconds — prevents the app from hanging forever
DEFAULT_TIMEOUT = (10, 60)
EXPORT_TIMEOUT = (10, 300)   # PBIX export / upload can legitimately take longer


class FabricClient:
    def __init__(self, access_token):
        self.access_token = access_token
        self.fabric_base_url = "https://api.fabric.microsoft.com/v1"
        self.pbi_base_url = "https://api.powerbi.com/v1.0/myorg"
        # A pooled session keeps TCP connections warm -> much faster for many items
        self.session = requests.Session()

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _get(self, url):
        response = self.session.get(url, headers=self.headers, timeout=DEFAULT_TIMEOUT)
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
        response = self.session.get(url, headers=self.headers, timeout=EXPORT_TIMEOUT)
        response.raise_for_status()
        return response.content

    def get_item_definition(self, workspace_id, item_id, format=None):
        url = f"{self.fabric_base_url}/workspaces/{workspace_id}/items/{item_id}/getDefinition"

        # Fabric expects `format` as a QUERY parameter (not a JSON body).
        params = {}
        if format:
            params["format"] = format

        response = self.session.post(url, headers=self.headers, params=params, timeout=DEFAULT_TIMEOUT)

        # Immediate success
        if response.status_code == 200:
            return response.json().get("definition", {})

        # Long-running operation
        if response.status_code == 202:
            op_url = response.headers.get("Location") or response.headers.get("Operation-Location")
            # Cap the wait between polls to 1-5s so large Retry-After values don't stall the app
            retry_after = min(max(self._safe_int(response.headers.get("Retry-After"), 2), 1), 5)
            if not op_url:
                raise Exception("Fabric accepted the request but returned no operation URL to poll for the definition.")

            for _ in range(40):  # ~ up to a couple of minutes max
                time.sleep(retry_after)
                op_resp = self.session.get(op_url, headers=self.headers, timeout=DEFAULT_TIMEOUT)
                op_resp.raise_for_status()
                op_json = op_resp.json()
                status = op_json.get("status", "")

                if status == "Succeeded":
                    # Result may be delivered via a Location header or the conventional /result path
                    result_url = op_resp.headers.get("Location") or f"{op_url}/result"
                    res_resp = self.session.get(result_url, headers=self.headers, timeout=EXPORT_TIMEOUT)
                    res_resp.raise_for_status()
                    res_json = res_resp.json()
                    return res_json.get("definition", res_json)
                elif status == "Failed":
                    err = op_json.get("error", {}) or {}
                    msg = err.get("message") or err.get("errorCode") or str(op_json)
                    logger.error(f"getDefinition operation failed: {op_json}")
                    raise Exception(f"Fabric could not export this item's definition: {msg}")
                # NotStarted / Running -> keep polling, honour any updated Retry-After (capped)
                retry_after = min(max(self._safe_int(op_resp.headers.get("Retry-After"), retry_after), 1), 5)

            raise Exception("Timed out waiting for Fabric to prepare the item definition (still running after a couple of minutes).")

        # Any other status code -> surface the real error message
        detail = self._extract_error(response)
        raise Exception(f"getDefinition returned HTTP {response.status_code}: {detail}")

    @staticmethod
    def _safe_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _extract_error(response):
        try:
            err_json = response.json()
            err = err_json.get("error", err_json)
            return err.get("message") or err.get("errorCode") or str(err_json)
        except Exception:
            return response.text or "No additional detail returned."

    def create_folder(self, workspace_id, folder_name, parent_folder_id=None):
        url = f"{self.fabric_base_url}/workspaces/{workspace_id}/folders"
        payload = {"displayName": folder_name}
        if parent_folder_id:
            payload["parentFolderId"] = parent_folder_id
        
        response = self.session.post(url, headers=self.headers, json=payload, timeout=DEFAULT_TIMEOUT)
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
            response = self.session.post(url, headers=headers, files=files, timeout=EXPORT_TIMEOUT)
            response.raise_for_status()
            
            import_info = response.json()
            import_id = import_info.get("id")

            # Polling for import completion (capped so it can't hang forever)
            for _ in range(150):
                time.sleep(2)
                status_res = self.get_import(workspace_id, import_id)
                state = status_res.get("importState")
                if state == "Succeeded":
                    return status_res
                elif state == "Failed":
                    raise Exception(f"Import Failed: {status_res}")
                elif state in ["Publishing", "Importing"]:
                    continue
            raise Exception("Import timed out: Power BI is still processing the file after several minutes.")

    def rebind_report(self, workspace_id, report_id, dataset_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/reports/{report_id}/Rebind"
        payload = {"datasetId": dataset_id}
        response = self.session.post(url, headers=self.headers, json=payload, timeout=DEFAULT_TIMEOUT)
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
        response = self.session.post(url, headers=self.headers, json=payload, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response

    def delete_report(self, workspace_id, report_id):
        url = f"{self.pbi_base_url}/groups/{workspace_id}/reports/{report_id}"
        response = self.session.delete(url, headers=self.headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response
