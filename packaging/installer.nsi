; packaging/installer.nsi
; NSIS installer for Recall Score (M2, NFR-02 AC-02.1/AC-02.3): a standard
; wizard (Welcome/Components/Directory/Start Menu/Install/Finish), installs
; to Program Files (per-machine, admin required - user's decision), and
; registers an Add/Remove Programs entry with a real uninstaller. Per-user
; app settings/per-score config (persistence/app_settings.py,
; persistence/score_config.py) live under each user's own AppData via
; QStandardPaths regardless of where the app binary is installed, so
; per-machine install does not make preferences shared across users.
;
; Self-contained - run directly, no /D defines needed. Run it from INSIDE
; this directory (not `makensis packaging\installer.nsi` from the repo root -
; NSIS 3.11's ${__FILEDIR__} preprocessor macro, used below to find the repo
; root, resolves to a doubled/wrong path when the script is passed as a
; relative path with a directory component; verified reproducible, only a
; bare filename or a fully-absolute script path resolves it correctly):
;     cd packaging
;     makensis installer.nsi
; Prerequisite: the PyInstaller bundle must already exist at dist\RecallScore
; (build it first with, from the repo root:
;     .venv\Scripts\python.exe -m PyInstaller packaging\RecallScore.spec --noconfirm
; ). packaging/build_installer.ps1 remains as an optional one-command wrapper
; that runs both steps (it invokes makensis with an absolute script path, so
; it isn't affected by the relative-path quirk above).
;
; Version comes from version.txt (repo root) - edit that file to change the
; version this build stamps into the installer filename/registry entry.
; Icon comes from packaging/icon.ico if present, else the installer/app use
; NSIS's default icon.

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define APP_NAME "Recall Score"
!define APP_EXE "RecallScore.exe"
!define COMPANY_NAME "Recall Score"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RecallScore"

!define REPO_ROOT "${__FILEDIR__}\.."
!define DIST_DIR "${REPO_ROOT}\dist\RecallScore"
!define OUT_DIR "${REPO_ROOT}\dist_installer"
!define VERSION_FILE "${REPO_ROOT}\version.txt"
!define ICON_PATH "${__FILEDIR__}\icon.ico"

; NSIS has no built-in !ifexist - this is the standard compile-time
; file-existence idiom: shell out to `if exist`, have it write a !define
; into a temp file only when true, !include that file, then clean up.
!tempfile _distcheck
!system 'if exist "${DIST_DIR}\${APP_EXE}" echo !define HAS_DIST > "${_distcheck}"'
!include "${_distcheck}"
!delfile "${_distcheck}"
!ifndef HAS_DIST
  !error "No ${APP_EXE} at ${DIST_DIR} - build the PyInstaller bundle first (see the header comment above)."
!endif

!tempfile _versioncheck
!system 'if exist "${VERSION_FILE}" echo !define HAS_VERSION_FILE > "${_versioncheck}"'
!include "${_versioncheck}"
!delfile "${_versioncheck}"
!ifndef HAS_VERSION_FILE
  !error "version.txt not found at ${VERSION_FILE} - create it with the version number to build, e.g. 2026.1.12"
!endif
!searchparse /file "${VERSION_FILE}" "" APP_VERSION

!system 'if not exist "${OUT_DIR}" mkdir "${OUT_DIR}"'

Name "${APP_NAME}"
OutFile "${OUT_DIR}\RecallScore-Setup-${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; --- UI ---
!define MUI_ABORTWARNING
!tempfile _iconcheck
!system 'if exist "${ICON_PATH}" echo !define HAS_ICON > "${_iconcheck}"'
!include "${_iconcheck}"
!delfile "${_iconcheck}"
!ifdef HAS_ICON
  !define MUI_ICON "${ICON_PATH}"
  !define MUI_UNICON "${ICON_PATH}"
!endif

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY

Var StartMenuFolder
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "HKLM"
!define MUI_STARTMENUPAGE_REGISTRY_KEY "${UNINST_KEY}"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "StartMenuFolder"
!insertmacro MUI_PAGE_STARTMENU StartMenuFolder $StartMenuFolder

!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; --- Install ---
Section "Recall Score (required)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${DIST_DIR}\*.*"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  !insertmacro MUI_STARTMENU_WRITE_BEGIN StartMenuFolder
    CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
    CreateShortCut "$SMPROGRAMS\$StartMenuFolder\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Uninstall ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
  !insertmacro MUI_STARTMENU_WRITE_END

  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "${COMPANY_NAME}"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Desktop Shortcut" SecDesktop
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

; --- Uninstall ---
Section "Uninstall"
  !insertmacro MUI_STARTMENU_GETFOLDER StartMenuFolder $StartMenuFolder
  Delete "$SMPROGRAMS\$StartMenuFolder\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall ${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\$StartMenuFolder"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"

  ; Deliberately does NOT touch per-user AppData settings/preferences
  ; (persistence/app_settings.py, persistence/score_config.py) - a plain
  ; uninstall shouldn't silently discard a user's saved display/voice
  ; preferences on the chance they reinstall later. Edit menu > "Open Local
  ; Folder" already exposes that folder if the user wants to clear it by
  ; hand (Ref 27 / G4).
  DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
