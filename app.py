import os
import sys
import threading
from flask import Flask, jsonify, request, render_template
import webview

# Handle PyInstaller one-file extraction directory
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'ui', 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'ui', 'static')
else:
    template_folder = "ui/templates"
    static_folder = "ui/static"

# Import our existing scripts and classes
from auth import get_access_token
from api_client import FabricClient
from downloader import download_pbix, download_pbir
from bulk_uploader import get_or_create_folder

app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

# Using "common" allows users from any organization to log in
TENANT_ID = "organizations"
client = None
current_user = "Not Authenticated"

# ----------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/auth", methods=["POST"])
def authenticate():
    global client, current_user
    try:
        access_token = get_access_token(TENANT_ID)
        client = FabricClient(access_token)
        
        import base64
        import json
        parts = access_token.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            payload += '=' * (-len(payload) % 4)
            decoded = json.loads(base64.b64decode(payload).decode("utf-8"))
            current_user = decoded.get("upn", decoded.get("unique_name", decoded.get("email", "Authenticated User")))
        else:
            current_user = "Authenticated User"
            
        return jsonify({"status": "success", "user": current_user})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 401

@app.route("/api/workspaces", methods=["GET"])
def get_workspaces():
    if not client:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    try:
        workspaces = client.get_workspaces()
        return jsonify({"status": "success", "workspaces": workspaces})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/workspaces/<workspace_id>/structure", methods=["GET"])
def get_workspace_structure(workspace_id):
    if not client:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    try:
        folders = client.get_folders(workspace_id)
        items = client.get_items(workspace_id)
        
        # Reports and Semantic Models
        reports = [i for i in items if i.get("type") in ["Report", "SemanticModel"]]
        
        return jsonify({
            "status": "success", 
            "folders": folders,
            "reports": reports
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/datasets/<workspace_id>", methods=["GET"])
def get_datasets(workspace_id):
    if not client:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    try:
        datasets = client.get_datasets(workspace_id)
        return jsonify({"status": "success", "datasets": datasets})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/select_folder", methods=["GET"])
def select_folder():
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Select Folder")
    root.destroy()
    
    return jsonify({"folder": folder_path})

@app.route("/api/select_files", methods=["GET"])
def select_files():
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    file_paths = filedialog.askopenfilenames(title="Select PBIX Files", filetypes=[("PBIX Files", "*.pbix")])
    root.destroy()
    
    return jsonify({"files": list(file_paths)})

@app.route("/api/download", methods=["POST"])
def download():
    data = request.json
    workspace_id = data.get("workspace_id")
    items = data.get("reports", [])  # List of dicts {id, name, type}
    base_download_dir = data.get("download_dir")
    
    if not base_download_dir or not os.path.exists(base_download_dir):
        return jsonify({"status": "error", "message": "Invalid download directory"}), 400
    
    summary = []
    
    for item in items:
        summary.append(_download_single_item(workspace_id, item, base_download_dir))
            
    return jsonify({"status": "success", "message": f"Download task finished. Check logs.", "summary": summary})


def _download_single_item(workspace_id, item, base_download_dir):
    """Downloads a single item and returns a detailed summary dict."""
    item_id = item["id"]
    safe_name = item["name"].replace("/", "").replace("\\", "")
    item_type = item.get("type", "Report")

    try:
        if item_type == "Report":
            pbir_success, pbir_reason = download_pbir(client, workspace_id, item_id, safe_name, base_download_dir, item_type=item_type)
            pbix_success, pbix_reason = download_pbix(client, workspace_id, item_id, safe_name, base_download_dir)

            success = pbir_success and pbix_success
            reasons = []
            if pbir_reason: reasons.append(f"Structure: {pbir_reason}")
            if pbix_reason: reasons.append(f"Binary: {pbix_reason}")
            reason_str = "  |  ".join(reasons)
        else:  # SemanticModel
            success, reason_str = download_pbir(client, workspace_id, item_id, safe_name, base_download_dir, item_type=item_type)

        status = "Success" if success else ("Partial" if item_type == "Report" and ("successfully" in reason_str.lower()) else "Failed")
        return {"name": safe_name, "type": item_type, "status": status, "reason": reason_str or "Completed."}
    except Exception as e:
        print(f"Error downloading {safe_name}: {e}")
        return {"name": safe_name, "type": item_type, "status": "Failed", "reason": f"Unexpected error: {str(e)}"}


@app.route("/api/download_one", methods=["POST"])
def download_one():
    """Downloads a single item — used by the UI progress bar loop."""
    if not client:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    data = request.json
    workspace_id = data.get("workspace_id")
    item = data.get("item")
    base_download_dir = data.get("download_dir")

    if not base_download_dir or not os.path.exists(base_download_dir):
        return jsonify({"status": "error", "message": "Invalid download directory"}), 400

    result = _download_single_item(workspace_id, item, base_download_dir)
    return jsonify({"status": "success", "result": result})


def _upload_single_file(workspace_id, file_path, target_dataset_id=None, target_folder_id=None):
    """Uploads a single PBIX file and returns a detailed summary dict."""
    f = os.path.basename(file_path)
    report_name = f[:-5] if f.lower().endswith(".pbix") else f

    if not file_path.lower().endswith(".pbix"):
        return {"name": report_name, "type": "PBIX", "status": "Failed", "reason": "Skipped: not a .pbix file."}

    try:
        # 1. Upload using "CreateOrOverwrite" collision behavior natively
        import_res = client.upload_pbix(workspace_id, file_path, report_name)
        imported_reports = import_res.get("reports", [])
        imported_datasets = import_res.get("datasets", [])

        if not imported_reports:
            ds_note = " A dataset/semantic model was created but no report was attached." if imported_datasets else ""
            return {"name": report_name, "type": "PBIX", "status": "Partial", "reason": f"Uploaded to workspace but no report object was returned.{ds_note}"}

        new_report_id = imported_reports[0].get("id")
        detail = f"Published successfully as report '{report_name}'."

        # 2. Rebind (if specified)
        if target_dataset_id:
            try:
                client.rebind_report(workspace_id, new_report_id, target_dataset_id)
                detail += f" Rebound to target dataset ({target_dataset_id[:8]}...)."
            except Exception as re:
                return {"name": report_name, "type": "PBIX", "status": "Partial", "reason": f"Uploaded OK, but rebind to dataset failed: {str(re)}"}

        return {"name": report_name, "type": "PBIX", "status": "Success", "reason": detail}
    except Exception as fe:
        err = str(fe)
        if "401" in err or "403" in err:
            reason = "Access denied. You need 'Member' or 'Contributor' rights on the target workspace to publish."
        elif "capacity" in err.lower():
            reason = "Upload blocked: the target workspace capacity is paused or over its limit."
        elif "Import Failed" in err:
            reason = f"Power BI rejected the file during import (corrupt PBIX, unsupported version, or model errors). Detail: {err}"
        else:
            reason = f"Upload failed: {err}"
        return {"name": report_name, "type": "PBIX", "status": "Failed", "reason": reason}


@app.route("/api/upload_one", methods=["POST"])
def upload_one():
    """Uploads a single file — used by the UI progress bar loop."""
    if not client:
        return jsonify({"status": "error", "message": "Not authenticated"}), 401
    data = request.json
    workspace_id = data.get("workspace_id")
    file_path = data.get("file_path")
    target_dataset_id = data.get("target_dataset_id")
    target_folder_id = data.get("target_folder_id")

    result = _upload_single_file(workspace_id, file_path, target_dataset_id, target_folder_id)
    return jsonify({"status": "success", "result": result})


@app.route("/api/upload", methods=["POST"])
def upload():
    data = request.json
    workspace_id = data.get("workspace_id")
    local_files = data.get("local_files", [])
    target_dataset_id = data.get("target_dataset_id")
    target_folder_id = data.get("target_folder_id")
    
    summary = []
    try:
        for file_path in local_files:
            summary.append(_upload_single_file(workspace_id, file_path, target_dataset_id, target_folder_id))

        return jsonify({"status": "success", "message": "Bulk upload task finished.", "summary": summary})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def start_flask():
    app.run(port=5000, debug=False)

if __name__ == "__main__":
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()
    
    webview.create_window("BI Artillery - Bulk Power BI Downloader/Uploader - v2.2.0", "http://localhost:5000", width=1200, height=800)
    webview.start()
