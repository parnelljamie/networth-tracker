; Phase 9: Inno Setup installer for Waymark.
; The app was called Passbook until 0.5.2. Upgrading from one of those installs moves it from
; Programs\Passbook to Programs\Waymark and swaps the Passbook Run value for a Waymark one; the
; app itself moves %APPDATA%\Passbook to %APPDATA%\Waymark on its first launch
; (app/core/paths.py migrate_legacy_data_dir). The fixed AppId is what makes it an upgrade.
; Built by scripts/build-installer.ps1 via: ISCC packaging\waymark.iss
; Expects the PyInstaller onedir build already at dist\Waymark\ (see waymark.spec) and
; reads the app version from backend\app\__init__.py via #define below.
;
; Install with lowest privileges is deliberate (Fixed decisions: per-user install, no admin
; prompt) -- do not change PrivilegesRequired without re-reading BUILD_PLAN.md Phase 9.

#define AppVersion GetFileVersion("..\dist\Waymark\Waymark.exe")
#define AppName "Waymark"

[Setup]
; Fixed AppId so upgrades install in place rather than side-by-side. Do not change.
AppId={{3F1F0D5E-6C1B-4E2A-9C6B-9B9E7D2A7E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Waymark
DefaultDirName={localappdata}\Programs\Waymark
; An upgrade from Passbook would otherwise stay in Programs\Passbook.
UsePreviousAppDir=no
DefaultGroupName=Waymark
; An upgrade from Passbook would otherwise keep the old Start menu folder.
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=WaymarkSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Waymark.exe
CloseApplications=yes
CloseApplicationsFilter=Waymark.exe,Passbook.exe
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start Waymark in the background when I sign in (so backups and price refreshes keep happening)"; GroupDescription: "Startup:"; Flags: unchecked

[InstallDelete]
; Shortcuts and program files left by installs from before the rename to Waymark. Only the
; program folder: the data folder in %APPDATA% is moved by the app, never deleted here.
Type: filesandordirs; Name: "{userprograms}\Passbook"
Type: files; Name: "{userdesktop}\Passbook.lnk"
Type: filesandordirs; Name: "{localappdata}\Programs\Passbook"

[Files]
Source: "..\dist\Waymark\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Waymark"; Filename: "{app}\Waymark.exe"
Name: "{group}\Uninstall Waymark"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Waymark"; Filename: "{app}\Waymark.exe"; Tasks: desktopicon

[Registry]
; Pre-rename installs started Programs\Passbook\Passbook.exe, which the upgrade removes.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Passbook"; Flags: deletevalue uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Waymark"; ValueData: """{app}\Waymark.exe"" --background"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Waymark.exe"; Description: "Launch Waymark"; Flags: nowait postinstall skipifsilent
; Settings -> Updates runs this installer with /SILENT after closing the app; reopen it afterwards.
Filename: "{app}\Waymark.exe"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
; Nothing here for app data -- deletion of %APPDATA%\Waymark is handled explicitly (with a
; confirmation, default No) in CurUninstallStepChanged below, per Fixed decisions.

[Code]
var
  DeleteDataOnUninstall: Boolean;

function IsWebView2Installed(): Boolean;
var
  Key: String;
  Installed: Boolean;
begin
  Installed := False;
  Key := 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  if RegKeyExists(HKLM, Key) then Installed := True;
  Key := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  if RegKeyExists(HKLM, Key) then Installed := True;
  if RegKeyExists(HKCU, Key) then Installed := True;
  Result := Installed;
end;

procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  // CloseApplications=yes already asks nicely for the foreground/windowed case; this is a
  // belt-and-braces fallback for a --background instance with no visible window to close.
  Exec('taskkill.exe', '/IM Waymark.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // An upgrade from before the rename: the old app has to let go of %APPDATA%\Passbook before
  // the new one can move it.
  Exec('taskkill.exe', '/IM Passbook.exe /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  if not IsWebView2Installed() then
  begin
    if MsgBox('Waymark needs the Microsoft Edge WebView2 runtime, which was not found on this PC.' + #13#10 +
       'Open the Microsoft download page now? (You can also install it later and re-run this setup.)',
       mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
  end;
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    KillRunningApp();
end;

procedure InitializeUninstallProgressForm();
begin
  KillRunningApp();
end;

function InitializeUninstall(): Boolean;
begin
  DeleteDataOnUninstall := (MsgBox('Also delete your Waymark data (accounts, balances, history, backups) in' + #13#10 +
    ExpandConstant('{%APPDATA}\Waymark') + '?' + #13#10#13#10 +
    'Choose No to keep your data -- for example if you plan to reinstall Waymark later.',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES);
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if DeleteDataOnUninstall then
    begin
      DelTree(ExpandConstant('{%APPDATA}\Waymark'), True, True, True);
      // Left behind only if the app never got to move it (see migrate_legacy_data_dir).
      DelTree(ExpandConstant('{%APPDATA}\Passbook'), True, True, True);
    end;
  end;
end;
