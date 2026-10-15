#ifndef ModelLabel
  #define ModelLabel "4B"
#endif
#ifndef AppSource
  #define AppSource "..\..\dist\windows\Yiyan"
#endif
#ifndef ReleaseOutput
  #define ReleaseOutput "..\..\dist\windows-offline"
#endif
[Setup]
AppId={{104AE585-268C-4579-9CD1-C70A22C20FD6}
AppName=译研 PaperBridge {#ModelLabel} 完整离线版
AppVersion=1.6.0
AppPublisher=hengyuwu-dot
AppPublisherURL=https://github.com/hengyuwu-dot/yiyan-paperbridge
DefaultDirName={localappdata}\Programs\Yiyan
DefaultGroupName=译研
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir={#ReleaseOutput}
OutputBaseFilename=Yiyan-1.6.0-Windows-x64-Offline-{#ModelLabel}-Setup
SetupIconFile=AppIcon.ico
UninstallDisplayIcon={app}\Yiyan.exe
Compression=lzma2/fast
SolidCompression=yes
DiskSpanning=yes
DiskSliceSize=1800000000
SlicesPerDisk=1
WizardStyle=modern
LicenseFile=..\..\LICENSE
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\译研"; Filename: "{app}\Yiyan.exe"
Name: "{autodesktop}\译研"; Filename: "{app}\Yiyan.exe"
Name: "{group}\Windows 安装教程"; Filename: "{app}\Windows-安装教程.md"

[Run]
Filename: "{app}\Runtime\Prerequisites\vc_redist.x64.exe"; Parameters: "/install /passive /norestart"; StatusMsg: "Preparing Microsoft Visual C++ runtime..."; Flags: shellexec waituntilterminated; Check: NeedsVC
Filename: "{sys}\icacls.exe"; Parameters: """{app}\Runtime\WebView2"" /grant *S-1-15-2-2:(OI)(CI)(RX) *S-1-15-2-1:(OI)(CI)(RX)"; Flags: runhidden waituntilterminated
Filename: "{app}\Yiyan.exe"; Description: "Launch Yiyan"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsVC: Boolean;
var InstalledMS, InstalledLS, RequiredMS, RequiredLS: Cardinal;
begin
  Result := True;
  if GetVersionNumbers(ExpandConstant('{sys}\vcruntime140.dll'), InstalledMS, InstalledLS) and
     GetVersionNumbers(ExpandConstant('{app}\Runtime\Prerequisites\vc_redist.x64.exe'), RequiredMS, RequiredLS) then
    Result := (InstalledMS < RequiredMS) or ((InstalledMS = RequiredMS) and (InstalledLS < RequiredLS));
end;
