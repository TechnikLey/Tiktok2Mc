; TikTok2MC — Windows Installer (NSIS Modern UI 2)
; =================================================

Unicode True
RequestExecutionLevel admin

!define PRODUCT_NAME "TikTok2MC"
!define PRODUCT_VERSION "v1.0.0"
!define PRODUCT_PUBLISHER "TechnikLey"
!define PRODUCT_WEB_SITE "https://github.com/TechnikLey/Tiktok2Mc"
!define PRODUCT_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

; ---------- Modern UI 2 ----------
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "WinVer.nsh"

; Installer properties
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
!ifdef OUT_FILE
  OutFile "${OUT_FILE}"
!else
  OutFile "..\build\TikTok2MC-${PRODUCT_VERSION}-Setup.exe"
!endif
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKLM "${PRODUCT_UNINSTALL_KEY}" "InstallDir"

; Request application privileges
RequestExecutionLevel admin

; ---------- Interface Settings ----------
!define MUI_ABORTWARNING
!define MUI_ICON ""
!define MUI_UNICON ""
!define MUI_WELCOMEFINISHPAGE_BITMAP ""
!define MUI_HEADERIMAGE ""

; ---------- Pages ----------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
Page custom StartupPage StartupPageLeave
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ---------- Languages ----------
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

; ---------- Custom Page: Startup Registration ----------
Var StartupCheckbox

Function StartupPage
  !insertmacro MUI_HEADER_TEXT "Startup Options" "Choose whether TikTok2MC starts automatically when you log in."
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateCheckBox} 0 0 100% 12u "Start TikTok2MC automatically when I log in"
  Pop $StartupCheckbox
  nsDialogs::Show
FunctionEnd

Function StartupPageLeave
  ${NSD_GetState} $StartupCheckbox $0
  StrCmp $0 "1" "" +2
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\start.exe"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
FunctionEnd

; ---------- Sections ----------

Section "TikTok2MC" SEC_APP
  SectionIn RO

  SetOutPath "$INSTDIR"
  SetOverwrite on

  ; Copy all release files
  File /r "..\build\release\*"

  ; Preserve existing user config
  IfFileExists "$INSTDIR\config\config.yaml" 0 +2
  SetOverwrite off
  File "..\build\release\config\config.yaml"
  SetOverwrite on

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry: uninstall info
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\start.exe,0"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegDword HKLM "${PRODUCT_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDword HKLM "${PRODUCT_UNINSTALL_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDword HKLM "${PRODUCT_UNINSTALL_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Desktop Shortcut" SEC_DESKTOP
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\start.exe" "" "$INSTDIR\start.exe" 0
SectionEnd

Section "Start Menu Shortcut" SEC_STARTMENU
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\TikTok2MC.lnk" "$INSTDIR\start.exe" "" "$INSTDIR\start.exe" 0
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
SectionEnd

; ---------- Section Descriptions ----------
LangString DESC_SEC_APP ${LANG_ENGLISH} "Core application files (required)."
LangString DESC_SEC_APP ${LANG_GERMAN} "Kernanwendungsdateien (erforderlich)."
LangString DESC_SEC_DESKTOP ${LANG_ENGLISH} "Create a shortcut on the desktop."
LangString DESC_SEC_DESKTOP ${LANG_GERMAN} "Verknüpfung auf dem Desktop erstellen."
LangString DESC_SEC_STARTMENU ${LANG_ENGLISH} "Create shortcuts in the Start Menu."
LangString DESC_SEC_STARTMENU ${LANG_GERMAN} "Verknüpfungen im Startmenü erstellen."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APP} $(DESC_SEC_APP)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} $(DESC_SEC_DESKTOP)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_STARTMENU} $(DESC_SEC_STARTMENU)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------- Uninstall ----------
Section "Uninstall"
  ; Remove shortcuts
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"

  ; Remove startup entry
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"

  ; Remove all installed files
  RMDir /r "$INSTDIR"

  ; Remove uninstall registry key
  DeleteRegKey HKLM "${PRODUCT_UNINSTALL_KEY}"
SectionEnd
