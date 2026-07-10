document.addEventListener('DOMContentLoaded', () => {
    
    // UI Elements
    const btnAuth = document.getElementById('btn-auth');
    const authPill = document.getElementById('auth-pill');
    const btnSignout = document.getElementById('btn-signout');
    const userDisplay = document.getElementById('user-display');
    const workspaceList = document.getElementById('workspace-list');
    const tableBody = document.getElementById('table-body');
    const currentWsLbl = document.getElementById('current-ws-lbl');
    const detailsPane = document.getElementById('details-pane');
    const detailsContent = document.getElementById('details-content');
    const statusWs = document.getElementById('status-ws');
    const statusTotals = document.getElementById('status-totals');
    
    const btnDownload = document.getElementById('btn-download');
    const btnUpload = document.getElementById('btn-upload');
    const btnSelectAll = document.getElementById('btn-select-all');
    const btnClearAll = document.getElementById('btn-clear-all');
    const btnRefresh = document.getElementById('btn-refresh');
    const checkAll = document.getElementById('check-all');

    let currentWorkspaceId = null;
    let currentFolderId = null;
    let folderBreadcrumbs = []; // Stack of {id, name}
    let allWorkspaceData = { folders: [], reports: [] };
    let loadedReports = [];

    // --- Actions ---

    // Authenticate
    btnAuth.addEventListener('click', async () => {
        tableBody.innerHTML = '<tr><td colspan="4">Authenticating... Check browser window.</td></tr>';
        
        try {
            const res = await fetch('/api/auth', { method: 'POST' });
            const data = await res.json();
            
            if (data.status === 'success') {
                btnAuth.style.display = 'none';
                authPill.style.display = 'flex';
                btnSignout.style.display = 'block';
                userDisplay.textContent = data.user;
                
                loadWorkspaces();
            } else {
                tableBody.innerHTML = `<tr><td colspan="4">Auth error: ${data.message}</td></tr>`;
            }
        } catch (e) {
            console.error(e);
            tableBody.innerHTML = `<tr><td colspan="4">Error connecting to local server.</td></tr>`;
        }
    });

    // Load Workspaces
    async function loadWorkspaces() {
        workspaceList.innerHTML = '<li>Loading...</li>';
        try {
            const res = await fetch('/api/workspaces');
            const data = await res.json();
            
            if (data.status === 'success') {
                workspaceList.innerHTML = '';
                const wss = data.workspaces;
                statusTotals.textContent = `${wss.length} Workspaces`;
                
                wss.forEach(ws => {
                    const li = document.createElement('li');
                    li.textContent = `📁 ${ws.displayName}`;
                    li.addEventListener('click', () => selectWorkspace(ws.id, ws.displayName, li));
                    workspaceList.appendChild(li);
                });
            } else {
                workspaceList.innerHTML = `<li>Error: ${data.message}</li>`;
            }
        } catch (e) {
            workspaceList.innerHTML = `<li>Error: ${e}</li>`;
        }
    }

    // Select Workspace
    async function selectWorkspace(id, name, liEl) {
        // UI Updates
        document.querySelectorAll('.workspace-list li').forEach(l => l.classList.remove('active'));
        if (liEl) liEl.classList.add('active');
        currentWsLbl.textContent = name;
        statusWs.textContent = `Workspace: ${name}`;
        currentWorkspaceId = id;
        detailsPane.style.display = 'none';
        
        btnDownload.disabled = true;
        btnUpload.disabled = false; // We can upload to a selected ws

        tableBody.innerHTML = '<tr><td colspan="4">Loading items...</td></tr>';

        try {
            const res = await fetch(`/api/workspaces/${id}/structure`);
            const data = await res.json();
            
            if (data.status === 'success') {
                allWorkspaceData = { folders: data.folders, reports: data.reports };
                
                // Render subfolders under the workspace li in the sidebar
                document.querySelectorAll('.folder-tree').forEach(el => el.remove());
                if (liEl) {
                    const treeHtml = buildFolderTree(allWorkspaceData.folders, null);
                    if (treeHtml) {
                        const treeContainer = document.createElement('div');
                        treeContainer.className = 'folder-tree';
                        treeContainer.innerHTML = treeHtml;
                        liEl.after(treeContainer);
                    }
                }
                
                // Start explorer view at the root of the workspace
                renderExplorer(null, null);
            } else {
                tableBody.innerHTML = `<tr><td colspan="4">Error: ${data.message}</td></tr>`;
            }
        } catch (e) {
            tableBody.innerHTML = `<tr><td colspan="4">Error: ${e}</td></tr>`;
        }
    }

    function buildFolderTree(folders, parentId) {
        if (!folders) return '';
        const children = folders.filter(f => (f.parentFolderId || null) === parentId);
        if (children.length === 0) return '';
        let html = '<ul style="list-style:none; padding-left:20px; font-size: 13px; margin: 4px 0;">';
        children.forEach(f => {
            html += `<li style="padding: 4px 0; color: #605e5c; cursor:pointer;" onclick="navigateExplorer('${f.id}','${f.displayName}')">📂 ${f.displayName}</li>`;
            html += buildFolderTree(folders, f.id);
        });
        html += '</ul>';
        return html;
    }

    // Expose a global function to easily hook into the explorer navigation
    window.navigateExplorer = function(folderId, folderName) {
        if (folderId === 'null') folderId = null;
        renderExplorer(folderId, folderName);
    };

    function renderExplorer(targetFolderId = null, folderName = null) {
        currentFolderId = targetFolderId;
        
        // Update breadcrumbs array
        if (targetFolderId === null) {
            folderBreadcrumbs = [];
        } else if (folderName) {
            // Check if navigating backwards up the chain
            const existingIdx = folderBreadcrumbs.findIndex(b => b.id === targetFolderId);
            if (existingIdx !== -1) {
                folderBreadcrumbs = folderBreadcrumbs.slice(0, existingIdx + 1);
            } else {
                folderBreadcrumbs.push({id: targetFolderId, name: folderName});
            }
        }

        // Render Breadcrumbs UI
        const breadContainer = document.getElementById('breadcrumbs');
        let breadHtml = `<span class="fabric-icon" style="cursor:pointer" onclick="navigateExplorer(null, null)">🗂</span> <span class="crumb-link" style="cursor:pointer" onclick="navigateExplorer(null, null)">Fabric</span> <span class="chevron">></span> <span style="cursor:pointer" onclick="navigateExplorer(null, null)">${currentWsLbl.textContent}</span>`;
        
        folderBreadcrumbs.forEach(b => {
             breadHtml += ` <span class="chevron">></span> <span class="crumb-link" style="cursor:pointer" onclick="navigateExplorer('${b.id}', '${b.name}')">${b.name}</span>`;
        });
        breadContainer.innerHTML = breadHtml;

        // Filter contents
        const childFolders = allWorkspaceData.folders.filter(f => (f.parentFolderId || null) === currentFolderId);
        const childReports = allWorkspaceData.reports.filter(r => (r.folderId || r.parentFolderId || null) === currentFolderId);

        renderTable(childReports, childFolders);
    }

    // Render Reports Table
    function renderTable(reports, folders = []) {
        loadedReports = reports;
        tableBody.innerHTML = '';
        
        if (reports.length === 0 && folders.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" class="empty-state">No items found in this workspace.</td></tr>';
            return;
        }

        // Render Folders
        folders.forEach(folder => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="col-check"></td>
                <td style="cursor:pointer;" class="crumb-link">📂 <strong>${folder.displayName}</strong></td>
                <td><span class="type-badge" style="border-color:#d29200; color:#d29200;">Folder</span></td>
                <td class="text-right">-</td>
            `;
            // Add click listener so clicking the folder navigates into it
            tr.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT') {
                    navigateExplorer(folder.id, folder.displayName);
                }
            });
            tableBody.appendChild(tr);
        });

        reports.forEach(report => {
            const tr = document.createElement('tr');
            
            // Checkbox
            const tdChk = document.createElement('td');
            tdChk.className = 'col-check';
            const chk = document.createElement('input');
            chk.type = 'checkbox';
            chk.className = 'report-chk';
            chk.value = report.id;
            chk.dataset.name = report.displayName;
            chk.dataset.type = report.type; // <-- Add Type Dataset
            chk.addEventListener('change', checkSelection);
            tdChk.appendChild(chk);
            
            // Name
            const tdName = document.createElement('td');
            let icon = report.type === 'SemanticModel' ? '🗄️' : '📊';
            tdName.innerHTML = `${icon} <strong>${report.displayName}</strong>`;
            
            // Type
            const tdType = document.createElement('td');
            let bcolor = report.type === 'SemanticModel' ? '#ff0055' : '#00f3ff';
            let typeLabel = report.type === 'SemanticModel' ? 'Semantic Model' : 'Report';
            tdType.innerHTML = `<span class="type-badge" style="border-color:${bcolor}; color:${bcolor};">${typeLabel}</span>`;
            
            // Size (dummy)
            const tdSize = document.createElement('td');
            tdSize.className = 'text-right';
            tdSize.textContent = '-';

            tr.appendChild(tdChk);
            tr.appendChild(tdName);
            tr.appendChild(tdType);
            tr.appendChild(tdSize);
            
            tr.addEventListener('click', (e) => {
                if(e.target.tagName !== 'INPUT') {
                    showDetails(report);
                }
            });

            tableBody.appendChild(tr);
        });
        
        // Reset the master checkbox when rendering a new table
        if(checkAll) checkAll.checked = false;
        checkSelection();
    }

    function checkSelection() {
        const checkboxes = document.querySelectorAll('.report-chk');
        const checked = document.querySelectorAll('.report-chk:checked');
        
        btnDownload.disabled = checked.length === 0;
        
        if (checkAll && checkboxes.length > 0) {
            checkAll.checked = (checked.length === checkboxes.length);
        }
    }

    // Master Checkbox Logic
    if (checkAll) {
        checkAll.addEventListener('change', (e) => {
            const checkboxes = document.querySelectorAll('.report-chk');
            checkboxes.forEach(chk => {
                chk.checked = e.target.checked;
            });
            checkSelection();
        });
    }

    // Top buttons logic
    if (btnSelectAll) {
        btnSelectAll.addEventListener('click', () => {
            if (checkAll) {
                checkAll.checked = true;
                const checkboxes = document.querySelectorAll('.report-chk');
                checkboxes.forEach(chk => chk.checked = true);
                checkSelection();
            }
        });
    }

    if (btnClearAll) {
        btnClearAll.addEventListener('click', () => {
            if (checkAll) {
                checkAll.checked = false;
                const checkboxes = document.querySelectorAll('.report-chk');
                checkboxes.forEach(chk => chk.checked = false);
                checkSelection();
            }
        });
    }

    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => {
            if (currentWorkspaceId) {
                const activeLi = document.querySelector('.workspace-list li.active');
                selectWorkspace(currentWorkspaceId, currentWsLbl.textContent, activeLi);
            }
        });
    }

    // --- Workspace filter (sidebar) ---
    const workspaceFilter = document.getElementById('workspace-filter');
    if (workspaceFilter) {
        workspaceFilter.addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            document.querySelectorAll('.workspace-list li').forEach(li => {
                li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
            });
        });
    }

    // --- Report/item filter (center table) ---
    const reportFilter = document.getElementById('report-filter');
    if (reportFilter) {
        reportFilter.addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            document.querySelectorAll('#table-body tr').forEach(tr => {
                if (tr.querySelector('.empty-state')) return;
                tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
            });
        });
    }

    function showDetails(report) {
        detailsPane.style.display = 'flex';
        detailsContent.innerHTML = `
            <div style="background:#fff; border:1px solid #0078d4; border-radius:4px; padding:10px; margin-bottom:15px;">
                <h4 style="margin:0 0 5px 0; color:#0b0c10;">${report.displayName}</h4>
                <div style="font-size:11px; color:#605e5c;">ID: ${report.id}</div>
            </div>
            <table style="width:100%; text-align:left;">
                <tr><td style="padding:4px 0; color:#605e5c;">Type</td><td style="color:#0b0c10;">${report.type === 'SemanticModel' ? 'Semantic Model' : 'Power BI Report'}</td></tr>
                <tr><td style="padding:4px 0; color:#605e5c;">Workspace</td><td style="color:#0b0c10;">${currentWsLbl.textContent}</td></tr>
            </table>
        `;
    }

    document.querySelector('.close-details').addEventListener('click', () => {
        detailsPane.style.display = 'none';
    });

    function showProgressModal(title, text) {
        detailsPane.style.display = 'flex';
        detailsContent.innerHTML = `
            <div style="background:#0b0c10; border:1px solid #00f3ff; box-shadow: 0 0 15px rgba(0,243,255,0.3); border-radius:8px; padding:20px; text-align:center;">
                <h3 style="margin-top:0; color:#00f3ff; text-shadow: 0 0 5px #00f3ff;">${title}</h3>
                <div class="spinner" style="margin: 20px auto; border: 4px solid #1f2833; border-top: 4px solid #00f3ff; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite;"></div>
                <p style="color:#c5c6c7; font-weight:bold;">${text}</p>
            </div>
            <style>@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
        `;
    }

    function showSummaryModal(title, summaryArray) {
        detailsPane.style.display = 'flex';
        let rows = summaryArray.map(s => `
            <tr>
                <td style="padding:8px 5px; border-bottom:1px solid #1f2833; color:${s.status === 'Success' ? '#45ff45' : (s.status === 'Partial' ? '#ffb900' : '#ff0055')};">${s.status}</td>
                <td style="padding:8px 5px; border-bottom:1px solid #1f2833; color:#c5c6c7;">${s.name} <br><span style="font-size:10px; color:#00f3ff;">${s.type ? s.type : ''}</span></td>
                <td style="padding:8px 5px; border-bottom:1px solid #1f2833; color:#c5c6c7; font-size:11px;">${s.reason || '-'}</td>
            </tr>
        `).join('');

        detailsContent.innerHTML = `
            <div style="background:#0b0c10; border:1px solid #00f3ff; box-shadow: 0 0 15px rgba(0,243,255,0.3); border-radius:8px; padding:15px; color:#c5c6c7;">
                <h3 style="margin-top:0; border-bottom:1px solid #1f2833; padding-bottom:10px; color:#00f3ff; text-shadow: 0 0 5px #00f3ff;">${title} Details</h3>
                <div style="max-height: 400px; overflow-y:auto;">
                    <table style="width:100%; border-collapse:collapse; text-align:left;">
                        <thead>
                            <tr>
                                <th style="border-bottom:2px solid #00f3ff; padding:5px; color:#00f3ff;">Status</th>
                                <th style="border-bottom:2px solid #00f3ff; padding:5px; color:#00f3ff;">Item</th>
                                <th style="border-bottom:2px solid #00f3ff; padding:5px; color:#00f3ff;">Message</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <button class="btn btn-blue" style="margin-top:15px; width:100%;" onclick="document.getElementById('details-pane').style.display='none'">Close</button>
            </div>
        `;
    }

    // ---------- Progress overlay helpers ----------
    const progressOverlay = document.getElementById('progress-overlay');
    const progressTitle = document.getElementById('progress-title');
    const progressFill = document.getElementById('progress-fill');
    const progressCount = document.getElementById('progress-count');
    const progressPercent = document.getElementById('progress-percent');
    const progressCurrent = document.getElementById('progress-current');
    const progressLog = document.getElementById('progress-log');
    const progressDone = document.getElementById('progress-done');

    function openProgress(title, mode, total) {
        progressTitle.textContent = title;
        progressFill.style.width = '0%';
        progressFill.className = 'progress-fill' + (mode === 'upload' ? ' upload' : '');
        progressCount.textContent = `0 / ${total}`;
        progressPercent.textContent = '0%';
        progressCurrent.textContent = 'Starting…';
        progressLog.innerHTML = '';
        progressDone.style.display = 'none';
        const ps = document.getElementById('progress-stats');
        if (ps) { ps.style.display = 'none'; ps.innerHTML = ''; }
        progressOverlay.style.display = 'flex';
    }

    function updateProgress(done, total, currentName) {
        const pct = total === 0 ? 0 : Math.round((done / total) * 100);
        progressFill.style.width = pct + '%';
        progressCount.textContent = `${done} / ${total}`;
        progressPercent.textContent = pct + '%';
        if (currentName) progressCurrent.textContent = currentName;
    }

    function appendProgressLog(result) {
        const li = document.createElement('li');
        const icon = result.status === 'Success' ? '✓' : (result.status === 'Partial' ? '◐' : '✕');
        li.innerHTML = `<span class="plog-status plog-${result.status}">${icon} ${result.status}</span>
                        <span><strong>${result.name}</strong><br><span style="color:#8a8886;">${result.reason || ''}</span></span>`;
        progressLog.appendChild(li);
        progressLog.scrollTop = progressLog.scrollHeight;
    }

    const progressStats = document.getElementById('progress-stats');
    function showProgressStats(summary) {
        const ok = summary.filter(s => s.status === 'Success').length;
        const partial = summary.filter(s => s.status === 'Partial').length;
        const fail = summary.filter(s => s.status === 'Failed').length;
        let html = `<span class="stat stat-ok">✓ ${ok} Succeeded</span>`;
        if (partial > 0) html += `<span class="stat stat-partial">◐ ${partial} Partial</span>`;
        if (fail > 0) html += `<span class="stat stat-fail">✕ ${fail} Failed</span>`;
        progressStats.innerHTML = html;
        progressStats.style.display = 'flex';
    }

    progressDone.addEventListener('click', () => {
        progressOverlay.style.display = 'none';
        showSummaryModal(progressDone.dataset.kind || 'Operation', window._lastSummary || []);
    });

    // ---------- Download Action (real progress bar) ----------
    btnDownload.addEventListener('click', async () => {
        const checked = document.querySelectorAll('.report-chk:checked');
        if (checked.length === 0 || !currentWorkspaceId) return;

        const folderRes = await fetch('/api/select_folder');
        const folderData = await folderRes.json();
        const downloadFolder = folderData.folder;
        if (!downloadFolder) return;

        const items = Array.from(checked).map(c => ({ id: c.value, name: c.dataset.name, type: c.dataset.type }));
        const summary = [];

        openProgress('⤓ Downloading Reports', 'download', items.length);
        btnDownload.disabled = true;

        for (let i = 0; i < items.length; i++) {
            updateProgress(i, items.length, `Downloading: ${items[i].name}`);
            try {
                const res = await fetch('/api/download_one', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ workspace_id: currentWorkspaceId, item: items[i], download_dir: downloadFolder })
                });
                const data = await res.json();
                const result = data.result || { name: items[i].name, type: items[i].type, status: 'Failed', reason: data.message || 'Unknown error' };
                summary.push(result);
                appendProgressLog(result);
            } catch (e) {
                const result = { name: items[i].name, type: items[i].type, status: 'Failed', reason: 'Connection error: ' + e };
                summary.push(result);
                appendProgressLog(result);
            }
            updateProgress(i + 1, items.length);
        }

        progressCurrent.textContent = 'All downloads complete.';
        window._lastSummary = summary;
        showProgressStats(summary);
        progressDone.dataset.kind = 'Download';
        progressDone.style.display = 'block';
        checkSelection();
    });

    // ---------- Upload flow (modal + real progress bar) ----------
    const uploadModal = document.getElementById('upload-modal');
    const uploadWsName = document.getElementById('upload-ws-name');
    const uploadFolderSelect = document.getElementById('upload-folder-select');
    const uploadDatasetSelect = document.getElementById('upload-dataset-select');
    const uploadFileList = document.getElementById('upload-file-list');
    const uploadFileCount = document.getElementById('upload-file-count');
    const btnPickFiles = document.getElementById('btn-pick-files');
    const uploadStart = document.getElementById('upload-start');
    let selectedUploadFiles = [];

    function closeUploadModal() { uploadModal.style.display = 'none'; }
    document.getElementById('upload-modal-close').addEventListener('click', closeUploadModal);
    document.getElementById('upload-cancel').addEventListener('click', closeUploadModal);

    btnUpload.addEventListener('click', async () => {
        if (!currentWorkspaceId) { alert('Please select a workspace first.'); return; }

        // Reset modal state
        uploadWsName.value = currentWsLbl.textContent;
        selectedUploadFiles = [];
        uploadFileList.innerHTML = '';
        uploadFileCount.textContent = 'No files selected';
        uploadStart.disabled = true;

        // Populate folder dropdown from loaded workspace folders
        uploadFolderSelect.innerHTML = '<option value="">📁 Workspace Root (no subfolder)</option>';
        (allWorkspaceData.folders || []).forEach(f => {
            const opt = document.createElement('option');
            opt.value = f.id;
            opt.textContent = '📂 ' + f.displayName;
            uploadFolderSelect.appendChild(opt);
        });

        // Populate dataset dropdown (fetch semantic models/datasets)
        uploadDatasetSelect.innerHTML = '<option value="">🔗 Keep dataset packaged inside PBIX (no rebind)</option>';
        try {
            const dsRes = await fetch(`/api/datasets/${currentWorkspaceId}`);
            const dsData = await dsRes.json();
            if (dsData.status === 'success') {
                (dsData.datasets || []).forEach(ds => {
                    const opt = document.createElement('option');
                    opt.value = ds.id;
                    opt.textContent = '🗄️ ' + (ds.name || ds.displayName || ds.id);
                    uploadDatasetSelect.appendChild(opt);
                });
            }
        } catch (e) { console.warn('Could not load datasets', e); }

        uploadModal.style.display = 'flex';
    });

    btnPickFiles.addEventListener('click', async () => {
        const fileRes = await fetch('/api/select_files');
        const fileData = await fileRes.json();
        const files = fileData.files || [];
        if (files.length === 0) return;

        selectedUploadFiles = files;
        uploadFileList.innerHTML = '';
        files.forEach(fp => {
            const name = fp.split(/[\\/]/).pop();
            const li = document.createElement('li');
            li.innerHTML = `📊 ${name}`;
            uploadFileList.appendChild(li);
        });
        uploadFileCount.textContent = `${files.length} file(s) selected`;
        uploadStart.disabled = false;
    });

    uploadStart.addEventListener('click', async () => {
        if (selectedUploadFiles.length === 0) return;
        const targetDataset = uploadDatasetSelect.value || null;
        const targetFolder = uploadFolderSelect.value || null;

        closeUploadModal();
        openProgress('⤒ Uploading Reports', 'upload', selectedUploadFiles.length);

        const summary = [];
        for (let i = 0; i < selectedUploadFiles.length; i++) {
            const fp = selectedUploadFiles[i];
            const name = fp.split(/[\\/]/).pop();
            updateProgress(i, selectedUploadFiles.length, `Uploading: ${name}`);
            try {
                const res = await fetch('/api/upload_one', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        workspace_id: currentWorkspaceId,
                        file_path: fp,
                        target_dataset_id: targetDataset,
                        target_folder_id: targetFolder
                    })
                });
                const data = await res.json();
                const result = data.result || { name: name, type: 'PBIX', status: 'Failed', reason: data.message || 'Unknown error' };
                summary.push(result);
                appendProgressLog(result);
            } catch (e) {
                const result = { name: name, type: 'PBIX', status: 'Failed', reason: 'Connection error: ' + e };
                summary.push(result);
                appendProgressLog(result);
            }
            updateProgress(i + 1, selectedUploadFiles.length);
        }

        progressCurrent.textContent = 'All uploads complete.';
        window._lastSummary = summary;
        showProgressStats(summary);
        progressDone.dataset.kind = 'Upload';
        progressDone.style.display = 'block';

        // Refresh workspace view to reveal newly uploaded reports
        if (currentWorkspaceId) {
            const activeLi = document.querySelector('.workspace-list li.active');
            selectWorkspace(currentWorkspaceId, currentWsLbl.textContent, activeLi);
        }
    });
});