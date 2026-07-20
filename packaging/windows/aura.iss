; AURA Windows installer — Cursor-style Inno Setup (modern wizard + brand art).
; Built by packaging/make_windows_installer.py — do not run by hand without defines.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MyAppSourceDir
  #define MyAppSourceDir "..\..\dist\AURA"
#endif
#ifndef MyAppOutputDir
  #define MyAppOutputDir "..\..\dist\releases"
#endif
#ifndef MyAppOutputBase
  #define MyAppOutputBase "AURA-0.0.0-win-x64"
#endif
#ifndef MyAppIcon
  #define MyAppIcon "..\..\assets\AURA.ico"
#endif
#ifndef MyWizardImage
  #define MyWizardImage "wizard-image.bmp"
#endif
#ifndef MyWizardSmallImage
  #define MyWizardSmallImage "wizard-small-image.bmp"
#endif
#ifndef MyLicenseFile
  #define MyLicenseFile "LICENSE.txt"
#endif

#define MyAppName "AURA"
#define MyAppPublisher "AURA"
#define MyAppURL "https://www.hiauraai.com"
#define MyAppExeName "AURA.exe"

[Setup]
AppId={{A8E3C4B1-7D2F-4E91-9B6A-1F0C5D8E2A74}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/download
AppUpdatesURL={#MyAppURL}/download
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#MyAppOutputDir}
OutputBaseFilename={#MyAppOutputBase}
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile={#MyLicenseFile}
WizardImageFile={#MyWizardImage}
WizardSmallImageFile={#MyWizardSmallImage}
WizardStyle=modern
WizardSizePercent=120
WizardImageStretch=yes
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=force
RestartApplications=no
ChangesAssociations=no
ShowLanguageDialog=no
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Create a Quick Launch icon"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; PyInstaller onedir payload (AURA.exe + _internal / deps)
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks"; Parameters: "/Delete /TN AURAWake /F"; Flags: runhidden; RunOnceId: "RemoveAuraWakeTask"
Filename: "{cmd}"; Parameters: "/c del /f /q ""%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AURA Wake.cmd"""; Flags: runhidden; RunOnceId: "RemoveAuraWakeStartup"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
