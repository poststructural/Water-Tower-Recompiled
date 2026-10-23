; Installer for the Animaniacs: The Great Edgar Hunt recomp launcher.
; Built by launcher/build_exe.py (ISCC /DAppVersion=x.y.z).
;
; Installs only the launcher, per user (no admin prompt). The launcher then
; asks for the player's own game files and builds the game from them; no game
; data or game code is in this installer.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C2E4B-6A8E-4C9B-9D51-AE7A1E5D0C3B}
AppName=Animaniacs Recompiled
AppVersion={#AppVersion}
AppPublisher=AnimaniacsRecompiled
AppPublisherURL=https://github.com/Unowa001/AnimaniacsRecompiled
DefaultDirName={localappdata}\Programs\AnimaniacsRecompiled
DefaultGroupName=Animaniacs Recompiled
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AnimaniacsLauncherSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\AnimaniacsLauncher.exe
SetupIconFile=..\animaniacs_launcher\assets\icon.ico
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\AnimaniacsLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Animaniacs Recompiled"; Filename: "{app}\AnimaniacsLauncher.exe"
Name: "{group}\Uninstall Animaniacs Recompiled"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Animaniacs Recompiled"; Filename: "{app}\AnimaniacsLauncher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AnimaniacsLauncher.exe"; Description: "Set up the game now"; Flags: nowait postinstall skipifsilent
; After a silent self-update, start the new launcher again.
Filename: "{app}\AnimaniacsLauncher.exe"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
; Builds, the source checkout and toolchains the launcher downloaded. Game
; saves (%LOCALAPPDATA%\AnimaniacsRecompiled, outside "launcher") are kept,
; and so is a game folder the player pointed at.
Type: filesandordirs; Name: "{localappdata}\AnimaniacsRecompiled\launcher"
