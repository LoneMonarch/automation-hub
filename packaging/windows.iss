#define AppVersion "1.0.4"
[Setup]
AppId={{532C48F1-5C64-4AA5-A3AD-551C6891E00A}
AppName=Automation Hub
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Automation Hub
DefaultGroupName=Automation Hub
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AutomationHub-Windows-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\AutomationHub.exe
[Files]
Source: "..\dist\AutomationHub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\Automation Hub"; Filename: "{app}\AutomationHub.exe"
Name: "{autodesktop}\Automation Hub"; Filename: "{app}\AutomationHub.exe"
[Run]
Filename: "{app}\AutomationHub.exe"; Description: "Open Automation Hub"; Flags: nowait postinstall skipifsilent
