; Script generated for Inno Setup 6
; HeadMouseAI Professional Windows Installer - Phase 11 Public Release

#define MyAppName "HeadMouseAI"
#define MyAppVersion "1.0.0-beta.2"
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
OutputDir=..\dist\installer
OutputBaseFilename=HeadMouseAI_Setup
SetupIconFile=..\assets\icons\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\assets\icons\app_icon.ico
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=HeadMouseAI - AI-Powered Hands-Free Windows Mouse
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=1.0.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: "..\dist\HeadMouseAI\HeadMouseAI.exe"; DestDir: "{app}"; Flags: ignoreversion
; Application configuration (editable in root of installed directory)
Source: "..\config.toml"; DestDir: "{app}"; Flags: ignoreversion
; Documentation & License
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\USER_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\RELEASE_NOTES.md"; DestDir: "{app}"; Flags: ignoreversion
; Application icons & artwork
Source: "..\assets\icons\app_icon.ico"; DestDir: "{app}\assets\icons"; Flags: ignoreversion
Source: "..\assets\icons\app_icon.png"; DestDir: "{app}\assets\icons"; Flags: ignoreversion
Source: "..\assets\images\splash_chrome_sculpture.png"; DestDir: "{app}\assets\images"; Flags: ignoreversion
; AI model file
Source: "..\assets\models\face_landmarker.task"; DestDir: "{app}\assets\models"; Flags: ignoreversion
; Internal bundled runtime dependencies
Source: "..\dist\HeadMouseAI\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.log,logs,logs\*"

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
