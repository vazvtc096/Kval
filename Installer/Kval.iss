; Kval Installer (Inno Setup)
; Features:
; 1) Add to PATH
; 2) Install for all users (via built-in privilege dialog)
; 3) Install VS Code extension (optional VSIX install through code/codium)
; 4) Add context menu to .kval files
; 5) Create desktop shortcut

[Setup]
AppId={{A0D9E2F4-2F1C-4C86-9E7E-7D6D1B81C7F0}
AppName=Kval
AppVersion=0.1.0
AppPublisher=Kval
DefaultDirName={autopf}\Kval
DefaultGroupName=Kval
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=KvalSetup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesEnvironment=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addpath"; Description: "Add to PATH"; Flags: unchecked
Name: "vscodeext"; Description: "Install language extension for IDEs (VS Code based)"; Flags: unchecked
Name: "ctxmenu"; Description: "Add context menu to .kval files"; Flags: unchecked
Name: "desktopicon"; Description: "Create desktop shortcut"; Flags: unchecked
Name: "savesource"; Description: "Save source code"; Flags: unchecked

[Files]
; Optional source mirror under {app}\src\Kval for reference/debugging.
; Runtime entry executables do not inject this path, so they won't import from it by default.
Source: "{#SourcePath}\..\*"; DestDir: "{app}\src\Kval"; Flags: recursesubdirs ignoreversion; Tasks: savesource; Excludes: ".git\*,.github\*,.pytest_cache\*,.ruff_cache\*,__pycache__\*,*.pyc,*.pyo,Installer\payload\*,Installer\payload-src\*,Installer\*.exe,Supports\Kval-language-support\node_modules\*,Supports\Kval-language-support\out\*,Tools\*"
Source: "{#SourcePath}\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourcePath}\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourcePath}\..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{#SourcePath}\..\pyproject.toml'))

Source: "{#SourcePath}\..\Lib\*"; DestDir: "{app}\Lib"; Flags: recursesubdirs ignoreversion; Excludes: "__pycache__\*,*.pyc,*.pyo"
Source: "{#SourcePath}\..\PyModules\*"; DestDir: "{app}\PyModules"; Flags: recursesubdirs ignoreversion; Excludes: "__pycache__\*,*.pyc,*.pyo"
Source: "{#SourcePath}\..\Doc\*"; DestDir: "{app}\Doc"; Flags: recursesubdirs ignoreversion

Source: "{#SourcePath}\..\bin\*.cmd"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#SourcePath}\payload\bin\*"; DestDir: "{app}\bin"; Flags: recursesubdirs ignoreversion
Source: "{#SourcePath}\assets\kval-language-support.vsix"; DestDir: "{app}\vscode"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{#SourcePath}\assets\kval-language-support.vsix'))

[Icons]
Name: "{group}\Kval CLI"; Filename: "{app}\bin\kval.exe"
Name: "{commondesktop}\Kval CLI"; Filename: "{app}\bin\kval.exe"; Tasks: desktopicon; Check: IsAdminInstallMode
Name: "{userdesktop}\Kval CLI"; Filename: "{app}\bin\kval.exe"; Tasks: desktopicon; Check: not IsAdminInstallMode

[Registry]
; Per-user file association/context menu when not elevated.
Root: HKCU; Subkey: "Software\Classes\.kval"; ValueType: string; ValueName: ""; ValueData: "KvalFile"; Tasks: ctxmenu; Check: not IsAdminInstallMode; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\KvalFile"; ValueType: string; ValueName: ""; ValueData: "Kval Source File"; Tasks: ctxmenu; Check: not IsAdminInstallMode; Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\KvalFile\shell\open"; ValueType: string; ValueName: ""; ValueData: "Edit (default)"; Tasks: ctxmenu; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Classes\KvalFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """notepad.exe"" ""%1"""; Tasks: ctxmenu; Check: not IsAdminInstallMode

Root: HKCU; Subkey: "Software\Classes\KvalFile\shell\run"; ValueType: string; ValueName: ""; ValueData: "Run with Kval"; Tasks: ctxmenu; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Classes\KvalFile\shell\run\command"; ValueType: string; ValueName: ""; ValueData: """{app}\bin\kvale.exe"" ""%1"""; Tasks: ctxmenu; Check: not IsAdminInstallMode

Root: HKCU; Subkey: "Software\Classes\KvalFile\shell\compile"; ValueType: string; ValueName: ""; ValueData: "Compile with Kval"; Tasks: ctxmenu; Check: not IsAdminInstallMode
Root: HKCU; Subkey: "Software\Classes\KvalFile\shell\compile\command"; ValueType: string; ValueName: ""; ValueData: """{app}\bin\kvalc.exe"" ""%1"""; Tasks: ctxmenu; Check: not IsAdminInstallMode

; Machine-wide association/context menu when elevated.
Root: HKCR; Subkey: ".kval"; ValueType: string; ValueName: ""; ValueData: "KvalFile"; Tasks: ctxmenu; Check: IsAdminInstallMode; Flags: uninsdeletekey
Root: HKCR; Subkey: "KvalFile"; ValueType: string; ValueName: ""; ValueData: "Kval Source File"; Tasks: ctxmenu; Check: IsAdminInstallMode; Flags: uninsdeletekey

Root: HKCR; Subkey: "KvalFile\shell\open"; ValueType: string; ValueName: ""; ValueData: "Edit (default)"; Tasks: ctxmenu; Check: IsAdminInstallMode
Root: HKCR; Subkey: "KvalFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """notepad.exe"" ""%1"""; Tasks: ctxmenu; Check: IsAdminInstallMode

Root: HKCR; Subkey: "KvalFile\shell\run"; ValueType: string; ValueName: ""; ValueData: "Run with Kval"; Tasks: ctxmenu; Check: IsAdminInstallMode
Root: HKCR; Subkey: "KvalFile\shell\run\command"; ValueType: string; ValueName: ""; ValueData: """{app}\bin\kvale.exe"" ""%1"""; Tasks: ctxmenu; Check: IsAdminInstallMode

Root: HKCR; Subkey: "KvalFile\shell\compile"; ValueType: string; ValueName: ""; ValueData: "Compile with Kval"; Tasks: ctxmenu; Check: IsAdminInstallMode
Root: HKCR; Subkey: "KvalFile\shell\compile\command"; ValueType: string; ValueName: ""; ValueData: """{app}\bin\kvalc.exe"" ""%1"""; Tasks: ctxmenu; Check: IsAdminInstallMode

[Code]
function NormalizePathList(Value: string): string;
begin
  Result := Value;
  while Pos(';;', Result) > 0 do
    StringChangeEx(Result, ';;', ';', True);
  if (Length(Result) > 0) and (Result[1] = ';') then
    Delete(Result, 1, 1);
  if (Length(Result) > 0) and (Result[Length(Result)] = ';') then
    Delete(Result, Length(Result), 1);
end;

function PathListContains(Value, Item: string): Boolean;
var
  S: string;
  P: Integer;
  Part: string;
begin
  Result := False;
  S := Value;
  while S <> '' do
  begin
    P := Pos(';', S);
    if P = 0 then
    begin
      Part := S;
      S := '';
    end
    else
    begin
      Part := Copy(S, 1, P - 1);
      Delete(S, 1, P);
    end;

    if (Part <> '') and (CompareText(Part, Item) = 0) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function PathListRemove(Value, Item: string): string;
var
  S: string;
  P: Integer;
  Part: string;
  OutValue: string;
begin
  OutValue := '';
  S := Value;
  while S <> '' do
  begin
    P := Pos(';', S);
    if P = 0 then
    begin
      Part := S;
      S := '';
    end
    else
    begin
      Part := Copy(S, 1, P - 1);
      Delete(S, 1, P);
    end;

    if (Part <> '') and (CompareText(Part, Item) <> 0) then
    begin
      if OutValue <> '' then
        OutValue := OutValue + ';';
      OutValue := OutValue + Part;
    end;
  end;
  Result := NormalizePathList(OutValue);
end;

procedure SetEnvPath(ForAllUsers: Boolean; NewValue: string);
begin
  if ForAllUsers then
    RegWriteExpandStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', NewValue)
  else
    RegWriteExpandStringValue(HKCU, 'Environment', 'Path', NewValue);
end;

function GetEnvPath(ForAllUsers: Boolean): string;
begin
  if ForAllUsers then
  begin
    if not RegQueryStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Result) then
      Result := '';
  end
  else
  begin
    if not RegQueryStringValue(HKCU, 'Environment', 'Path', Result) then
      Result := '';
  end;
end;

procedure AddBinToPathIfSelected();
var
  ForAllUsers: Boolean;
  PathValue: string;
  BinDir: string;
begin
  if not WizardIsTaskSelected('addpath') then
    Exit;

  ForAllUsers := IsAdminInstallMode;
  BinDir := ExpandConstant('{app}\bin');
  PathValue := GetEnvPath(ForAllUsers);

  if not PathListContains(PathValue, BinDir) then
  begin
    if (PathValue <> '') and (PathValue[Length(PathValue)] <> ';') then
      PathValue := PathValue + ';';
    PathValue := NormalizePathList(PathValue + BinDir);
    SetEnvPath(ForAllUsers, PathValue);
  end;
end;

procedure RemoveBinFromPathIfPresent(ForAllUsers: Boolean);
var
  PathValue: string;
  BinDir: string;
begin
  BinDir := ExpandConstant('{app}\bin');
  PathValue := GetEnvPath(ForAllUsers);
  if PathValue = '' then
    Exit;

  PathValue := PathListRemove(PathValue, BinDir);
  SetEnvPath(ForAllUsers, PathValue);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    AddBinToPathIfSelected();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    if IsAdminInstallMode then
      RemoveBinFromPathIfPresent(True)
    else
      RemoveBinFromPathIfPresent(False);
  end;
end;

[Run]
Filename: "{cmd}"; Parameters: "/c where code >nul 2>nul && code --install-extension ""{app}\vscode\kval-language-support.vsix"" --force"; Tasks: vscodeext; Flags: runhidden
Filename: "{cmd}"; Parameters: "/c where codium >nul 2>nul && codium --install-extension ""{app}\vscode\kval-language-support.vsix"" --force"; Tasks: vscodeext; Flags: runhidden
Filename: "{cmd}"; Parameters: "/c where code-insiders >nul 2>nul && code-insiders --install-extension ""{app}\vscode\kval-language-support.vsix"" --force"; Tasks: vscodeext; Flags: runhidden

