[Setup]
AppName=BI Artillery
AppVersion=1.0
DefaultDirName={pf}\BI Artillery
DefaultGroupName=BI Artillery
OutputDir=C:\Users\arsha\PowerBIDownloader\Output
OutputBaseFilename=BI_Artillery_Installer
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "C:\Users\arsha\PowerBIDownloader\dist\BI Artillery.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\BI Artillery"; Filename: "{app}\BI Artillery.exe"
Name: "{commondesktop}\BI Artillery"; Filename: "{app}\BI Artillery.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
