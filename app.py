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

TENANT_ID = "a3c75d30-dfe5-4bd3-9fae-5e9fcc0d0997"
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
        item_id = item["id"]
        safe_name = item["name"].replace("/", "").replace("\\", "")
        item_type = item.get("type", "Report")
        
        try:
            if item_type == "Report":
                pbir_success, pbir_reason = download_pbir(client, workspace_id, item_id, safe_name, base_download_dir, item_type=item_type)
                pbix_success, pbix_reason = download_pbix(client, workspace_id, item_id, safe_name, base_download_dir)
                
                success = pbir_success and pbix_success
                reasons = []
                if not pbir_success: reasons.append(pbir_reason)
                if not pbix_success: reasons.append(pbix_reason)
                reason_str = " | ".join(reasons)
            else: # SemanticModel
                success, reason_str = download_pbir(client, workspace_id, item_id, safe_name, base_download_dir, item_type=item_type)
            
            if success:
                summary.append({"name": safe_name, "type": item_type, "status": "Success", "reason": "Successfully downloaded entirely."})
            else:
                summary.append({"name": safe_name, "type": item_type, "status": "Failed", "reason": reason_str or "Failed during download operation"})
        except Exception as e:
            print(f"Error downloading {safe_name}: {e}")
            summary.append({"name": safe_name, "type": item_type, "status": "Failed", "reason": str(e)})
            
    return jsonify({"status": "success", "message": f"Download task finished. Check logs.", "summary": summary})

@app.route("/api/upload", methods=["POST"])
def upload():
    data = request.json
    workspace_id = data.get("workspace_id")
    local_files = data.get("local_files", [])
    target_dataset_id = data.get("target_dataset_id")
    
    summary = []
    try:
        for file_path in local_files:
            if file_path.lower().endswith(".pbix"):
                f = os.path.basename(file_path)
                report_name = f[:-5]
                
                try:
                    # 1. Upload using "CreateOrOverwrite" collision behavior natively
                    import_res = client.upload_pbix(workspace_id, file_path, report_name)
                    imported_reports = import_res.get("reports", [])
                    if not imported_reports: 
                        summary.append({"name": report_name, "status": "Failed", "reason": "No reports returned after upload (only dataset)"})
                        continue
                        
                    new_report_id = imported_reports[0].get("id")
                    
                    # 2. Rebind (if specified)
                    if target_dataset_id:
                        client.rebind_report(workspace_id, new_report_id, target_dataset_id)
                        
                    summary.append({"name": report_name, "status": "Success", "reason": "Uploaded & Rebound" if target_dataset_id else "Uploaded (CreateOrOverwrite)"})
                except Exception as fe:
                    summary.append({"name": report_name, "status": "Failed", "reason": str(fe)})

        return jsonify({"status": "success", "message": "Bulk upload task finished.", "summary": summary})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def start_flask():
    app.run(port=5000, debug=False)

if __name__ == "__main__":
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()
    
    webview.create_window("BI Artillery - Bulk Power BI Downloader/Uploader - v2.1.0", "http://localhost:5000", width=1200, height=800)
    webview.start()
