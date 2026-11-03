#define AppName "DocFLow"
#define AppVersion "2.0.2"
#define AppPublisher "hndlab.dev.br"
#define AppExeName "DocFLow.exe"

[Setup]
AppId={{9B741DAB-4A2E-438B-85E7-58C63D4A3527}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Instala por usuario, sem pedir administrador: {autopf} vira %LOCALAPPDATA%\Programs e os
; atalhos vao para o menu Iniciar do usuario. Os dados ja ficam em %APPDATA%\DocFLow.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist_installer
OutputBaseFilename=DocFLow-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\icons\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#AppVersion}
; Atualizacao automatica: o DocFlow baixa este instalador e roda com /VERYSILENT
; /CLOSEAPPLICATIONS /RELAUNCH=1 - fecha o sistema aberto, instala por cima e abre de novo.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "..\..\dist\DocFLow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExeName}"; Flags: nowait; Check: ReabrirDepoisDeAtualizar

[Code]
function ReabrirDepoisDeAtualizar: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
