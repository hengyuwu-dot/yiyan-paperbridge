#define AppVersion "1.5.0"
[Setup]
AppId={{104AE585-268C-4579-9CD1-C70A22C20FD6}
AppName=译研 PaperBridge
AppVersion={#AppVersion}
AppPublisher=hengyuwu-dot
AppPublisherURL=https://github.com/hengyuwu-dot/yiyan-paperbridge
DefaultDirName={localappdata}\Programs\Yiyan
DefaultGroupName=译研
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir=..\..\dist\windows
OutputBaseFilename=Yiyan-1.5.0-Windows-x64-Setup
SetupIconFile=AppIcon.ico
UninstallDisplayIcon={app}\Yiyan.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\windows\Yiyan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\译研"; Filename: "{app}\Yiyan.exe"
Name: "{autodesktop}\译研"; Filename: "{app}\Yiyan.exe"
Name: "{group}\Windows 安装教程"; Filename: "{app}\Windows-安装教程.md"

[Run]
Filename: "{app}\Yiyan.exe"; Description: "Launch Yiyan"; Flags: nowait postinstall skipifsilent
