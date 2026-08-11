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
; Not meant to be invoked directly - packaging/build_installer.ps1 passes
; /DAPP_VERSION, /DDIST_DIR, /DOUT_DIR (and /DICON_PATH if the user has
; supplied packaging/icon.ico) on the makensis command line.

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define APP_NAME "Recall Score"
!define APP_EXE "RecallScore.exe"
!define COMPANY_NAME "Recall Score"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\RecallScore"

!ifndef APP_VERSION
  !define APP_VERSION "0.0.0"
!endif
!ifndef DIST_DIR
  !error "DIST_DIR not defined - run via packaging/build_installer.ps1, not makensis directly."
!endif
!ifndef OUT_DIR
  !error "OUT_DIR not defined - run via packaging/build_installer.ps1, not makensis directly."
!endif

Name "${APP_NAME}"
OutFile "${OUT_DIR}\RecallScore-Setup-${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; --- UI ---
!define MUI_ABORTWARNING
!ifdef ICON_PATH
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
