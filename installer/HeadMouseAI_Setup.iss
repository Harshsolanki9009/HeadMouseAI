; Script generated for Inno Setup 6
; HeadMouseAI Professional Windows Installer - Phase 11 Public Release

#define MyAppName "HeadMouseAI"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "ACROPOLIANS"
#define MyAppURL "https://github.com/Harshsolanki9009/HeadMouseAI"
#define MyAppExeName "HeadMouseAI.exe"

[Setup]
AppId={{E82956B3-596A-4A0B-8833-D608F796C9D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE.txt
OutputDir=..\dist
OutputBaseFilename=HeadMouseAI-Setup
SetupIconFile=..\assets\icons\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\assets\icons\app_icon.ico
VersionInfoVersion=2.1.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=HeadMouseAI - Autonomous AI Computer-Use Agent & Hands-Free Vision Control
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=2.1.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\HeadMouseAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.log,logs,logs\*"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icons\app_icon.ico"
Name: "{group}\User Guide"; Filename: "{app}\USER_GUIDE.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icons\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\logs"
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}"
