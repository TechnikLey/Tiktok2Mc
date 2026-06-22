; TikTok2MC — Windows Installer (NSIS Modern UI 2)
; =================================================
; Supports Basic and Advanced installation modes.

Unicode True
RequestExecutionLevel admin
ManifestDPIAware true

!define PRODUCT_NAME "TikTok2MC"
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "v1.0.0"
!endif
!define PRODUCT_PUBLISHER "TechnikLey"
!define PRODUCT_WEB_SITE "https://github.com/TechnikLey/Tiktok2Mc"
!define PRODUCT_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

; ---------- Modern UI 2 ----------
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "WinVer.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

; Installer properties
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
!ifdef OUT_FILE
  OutFile "${OUT_FILE}"
!else
  OutFile "..\build\TikTok2MC-${PRODUCT_VERSION}-Setup.exe"
!endif
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKLM "${PRODUCT_UNINSTALL_KEY}" "InstallDir"

; ---------- Interface Settings ----------
!define MUI_ABORTWARNING

; ---------- Pages ----------
; Installation type selection (always first)
Page custom InstallTypeCreate InstallTypeLeave

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY

; Advanced-only pages (skip logic inside each Create function)
Page custom AdvancedComponentsCreate AdvancedComponentsLeave
Page custom GuiModeCreate GuiModeLeave
Page custom JavaPortCreate JavaPortLeave
Page custom StartupPageCreate StartupPageLeave

!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ---------- Languages ----------
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

; ---------- Language Selection on Startup ----------
Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

; ---------- Variables ----------
Var InstallType            ; 0=Basic, 1=Advanced
Var hBasicRadio
Var hAdvancedRadio

Var AdvancedComponents     ; bit flags: 1=Plugins, 2=MCServer, 4=Docs
Var hPluginCheck
Var hMCCheck
Var hDocsCheck

Var GuiDefaultMode         ; 0=gui.exe, 1=start.exe
Var hGuiModeGui
Var hGuiModeStart

Var JavaPath               ; Custom Java path
Var ApiPort                ; API server port
Var hJavaPathText
Var hApiPortText

Var StartupCheckbox

; ---- Radio button mutual exclusion ----
Function InstallTypeRadioClick
  Pop $R0
  ${NSD_GetState} $hBasicRadio $R1
  ${If} $R1 == ${BST_CHECKED}
    ${NSD_Uncheck} $hAdvancedRadio
  ${Else}
    ${NSD_Uncheck} $hBasicRadio
  ${EndIf}
FunctionEnd

Function GuiModeRadioClick
  Pop $R0
  ${NSD_GetState} $hGuiModeGui $R1
  ${If} $R1 == ${BST_CHECKED}
    ${NSD_Uncheck} $hGuiModeStart
  ${Else}
    ${NSD_Uncheck} $hGuiModeGui
  ${EndIf}
FunctionEnd

; =============================================================
; PAGE: Installation Type (Basic / Advanced)
; =============================================================
LangString INSTALLTYPE_TITLE ${LANG_ENGLISH} "Installation Type"
LangString INSTALLTYPE_SUBTITLE ${LANG_ENGLISH} "Choose the installation mode."
LangString INSTALLTYPE_HEADER ${LANG_ENGLISH} "Installation Type"
LangString INSTALLTYPE_BASIC ${LANG_ENGLISH} "Basic Installation (recommended)"
LangString INSTALLTYPE_BASIC_DESC ${LANG_ENGLISH} "Installs TikTok2MC with standard settings. Suitable for most users."
LangString INSTALLTYPE_ADVANCED ${LANG_ENGLISH} "Advanced Installation"
LangString INSTALLTYPE_ADVANCED_DESC ${LANG_ENGLISH} "Configure components, GUI mode, Java path, port, and autostart behavior."

LangString INSTALLTYPE_TITLE ${LANG_GERMAN} "Installationstyp"
LangString INSTALLTYPE_SUBTITLE ${LANG_GERMAN} "Wählen Sie den Installationsmodus."
LangString INSTALLTYPE_HEADER ${LANG_GERMAN} "Installationstyp"
LangString INSTALLTYPE_BASIC ${LANG_GERMAN} "Basic-Installation (empfohlen)"
LangString INSTALLTYPE_BASIC_DESC ${LANG_GERMAN} "Installiert TikTok2MC mit Standardeinstellungen. Geeignet für die meisten Benutzer."
LangString INSTALLTYPE_ADVANCED ${LANG_GERMAN} "Erweiterte Installation"
LangString INSTALLTYPE_ADVANCED_DESC ${LANG_GERMAN} "Konfigurieren Sie Komponenten, GUI-Modus, Java-Pfad, Port und Autostart-Verhalten."

Function InstallTypeCreate
  !insertmacro MUI_HEADER_TEXT "$(INSTALLTYPE_TITLE)" "$(INSTALLTYPE_SUBTITLE)"
  nsDialogs::Create 1018
  Pop $0

  ${NSD_CreateLabel} 0 0 100% 24u "$(INSTALLTYPE_HEADER)"
  Pop $0

  ${NSD_CreateRadioButton} 0 28 100% 20u "$(INSTALLTYPE_BASIC)"
  Pop $hBasicRadio
  ${NSD_OnClick} $hBasicRadio InstallTypeRadioClick

  ${NSD_CreateLabel} 0 52 100% 40u "$(INSTALLTYPE_BASIC_DESC)"
  Pop $0

  ${NSD_CreateRadioButton} 0 96 100% 20u "$(INSTALLTYPE_ADVANCED)"
  Pop $hAdvancedRadio
  ${NSD_OnClick} $hAdvancedRadio InstallTypeRadioClick

  ${NSD_CreateLabel} 0 120 100% 40u "$(INSTALLTYPE_ADVANCED_DESC)"
  Pop $0

  ; Default: Basic
  ${If} $InstallType == ""
    StrCpy $InstallType 0
  ${EndIf}
  ${If} $InstallType == 0
    ${NSD_Check} $hBasicRadio
  ${Else}
    ${NSD_Check} $hAdvancedRadio
  ${EndIf}

  nsDialogs::Show
FunctionEnd

Function InstallTypeLeave
  ${NSD_GetState} $hBasicRadio $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $InstallType 0
  ${Else}
    StrCpy $InstallType 1
  ${EndIf}
FunctionEnd

; =============================================================
; PAGE: Advanced Components (Plugins, MC Server, Docs)
; =============================================================
LangString COMP_TITLE ${LANG_ENGLISH} "Advanced Components"
LangString COMP_SUBTITLE ${LANG_ENGLISH} "Select optional components to install."
LangString COMP_PLUGINS ${LANG_ENGLISH} "Plugins (deathcounter, spotify, timer, wincounter)"
LangString COMP_MC ${LANG_ENGLISH} "Minecraft Server (server.jar, tools)"
LangString COMP_DOCS ${LANG_ENGLISH} "Documentation (GUIDE, CHANGELOG, dev-books)"

LangString COMP_TITLE ${LANG_GERMAN} "Erweiterte Komponenten"
LangString COMP_SUBTITLE ${LANG_GERMAN} "Wählen Sie optionale Komponenten zur Installation."
LangString COMP_PLUGINS ${LANG_GERMAN} "Plugins (deathcounter, spotify, timer, wincounter)"
LangString COMP_MC ${LANG_GERMAN} "Minecraft Server (server.jar, tools)"
LangString COMP_DOCS ${LANG_GERMAN} "Dokumentation (GUIDE, CHANGELOG, dev-books)"

Function AdvancedComponentsCreate
  ${If} $InstallType == 0
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(COMP_TITLE)" "$(COMP_SUBTITLE)"
  nsDialogs::Create 1018
  Pop $0

  ${NSD_CreateCheckBox} 0 0 100% 20u "$(COMP_PLUGINS)"
  Pop $hPluginCheck
  ${If} $AdvancedComponents & 1
    ${NSD_Check} $hPluginCheck
  ${Else}
    ${NSD_Uncheck} $hPluginCheck
  ${EndIf}

  ${NSD_CreateCheckBox} 0 24 100% 20u "$(COMP_MC)"
  Pop $hMCCheck
  ${If} $AdvancedComponents & 2
    ${NSD_Check} $hMCCheck
  ${Else}
    ${NSD_Uncheck} $hMCCheck
  ${EndIf}

  ${NSD_CreateCheckBox} 0 48 100% 20u "$(COMP_DOCS)"
  Pop $hDocsCheck
  ${If} $AdvancedComponents & 4
    ${NSD_Check} $hDocsCheck
  ${Else}
    ${NSD_Uncheck} $hDocsCheck
  ${EndIf}

  ; Default: all selected
  ${If} $AdvancedComponents == 0
    IntOp $AdvancedComponents $AdvancedComponents | 1
    IntOp $AdvancedComponents $AdvancedComponents | 2
    IntOp $AdvancedComponents $AdvancedComponents | 4
    ${NSD_Check} $hPluginCheck
    ${NSD_Check} $hMCCheck
    ${NSD_Check} $hDocsCheck
  ${EndIf}

  nsDialogs::Show
FunctionEnd

Function AdvancedComponentsLeave
  StrCpy $AdvancedComponents 0
  ${NSD_GetState} $hPluginCheck $0
  ${If} $0 == ${BST_CHECKED}
    IntOp $AdvancedComponents $AdvancedComponents | 1
  ${EndIf}
  ${NSD_GetState} $hMCCheck $0
  ${If} $0 == ${BST_CHECKED}
    IntOp $AdvancedComponents $AdvancedComponents | 2
  ${EndIf}
  ${NSD_GetState} $hDocsCheck $0
  ${If} $0 == ${BST_CHECKED}
    IntOp $AdvancedComponents $AdvancedComponents | 4
  ${EndIf}
FunctionEnd

; =============================================================
; PAGE: GUI Default Mode
; =============================================================
LangString GUI_TITLE ${LANG_ENGLISH} "GUI Default Mode"
LangString GUI_SUBTITLE ${LANG_ENGLISH} "Choose the default application mode for desktop shortcuts."
LangString GUI_GUI ${LANG_ENGLISH} "GUI Mode (gui.exe)"
LangString GUI_GUI_DESC ${LANG_ENGLISH} "Opens the graphical user interface (recommended)"
LangString GUI_START ${LANG_ENGLISH} "Full System Mode (start.exe)"
LangString GUI_START_DESC ${LANG_ENGLISH} "Starts the complete stack including API and Minecraft server"

LangString GUI_TITLE ${LANG_GERMAN} "GUI-Standardmodus"
LangString GUI_SUBTITLE ${LANG_GERMAN} "Wählen Sie den Standardmodus für Desktop-Verknüpfungen."
LangString GUI_GUI ${LANG_GERMAN} "GUI-Modus (gui.exe)"
LangString GUI_GUI_DESC ${LANG_GERMAN} "Öffnet die grafische Benutzeroberfläche (empfohlen)"
LangString GUI_START ${LANG_GERMAN} "Full System Modus (start.exe)"
LangString GUI_START_DESC ${LANG_GERMAN} "Startet den vollständigen Stack inklusive API und Minecraft-Server"

Function GuiModeCreate
  ${If} $InstallType == 0
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(GUI_TITLE)" "$(GUI_SUBTITLE)"
  nsDialogs::Create 1018
  Pop $0

  ${NSD_CreateRadioButton} 0 0 100% 20u "$(GUI_GUI)"
  Pop $hGuiModeGui
  ${NSD_OnClick} $hGuiModeGui GuiModeRadioClick

  ${NSD_CreateLabel} 0 24 100% 20u "$(GUI_GUI_DESC)"
  Pop $0

  ${NSD_CreateRadioButton} 0 52 100% 20u "$(GUI_START)"
  Pop $hGuiModeStart
  ${NSD_OnClick} $hGuiModeStart GuiModeRadioClick

  ${NSD_CreateLabel} 0 76 100% 20u "$(GUI_START_DESC)"
  Pop $0

  ; Default: GUI Mode (true)
  ${If} $GuiDefaultMode == ""
    StrCpy $GuiDefaultMode 0
  ${EndIf}
  ${If} $GuiDefaultMode == 0
    ${NSD_Check} $hGuiModeGui
  ${Else}
    ${NSD_Check} $hGuiModeStart
  ${EndIf}

  nsDialogs::Show
FunctionEnd

Function GuiModeLeave
  ${NSD_GetState} $hGuiModeGui $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $GuiDefaultMode 0
  ${Else}
    StrCpy $GuiDefaultMode 1
  ${EndIf}
FunctionEnd

; =============================================================
; PAGE: Java Path & API Port
; =============================================================
LangString JAVA_TITLE ${LANG_ENGLISH} "Java & Port Configuration"
LangString JAVA_SUBTITLE ${LANG_ENGLISH} "Configure the Java runtime path and API server port."
LangString JAVA_PATH_LABEL ${LANG_ENGLISH} "Java executable path (leave empty for auto-detect):"
LangString JAVA_PORT_LABEL ${LANG_ENGLISH} "API server port (default: 29185):"

LangString JAVA_TITLE ${LANG_GERMAN} "Java- & Port-Konfiguration"
LangString JAVA_SUBTITLE ${LANG_GERMAN} "Konfigurieren Sie den Java-Pfad und den API-Server-Port."
LangString JAVA_PATH_LABEL ${LANG_GERMAN} "Java-Programmpfad (leer lassen für Auto-Erkennung):"
LangString JAVA_PORT_LABEL ${LANG_GERMAN} "API-Server-Port (Standard: 29185):"

Function JavaPortCreate
  ${If} $InstallType == 0
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(JAVA_TITLE)" "$(JAVA_SUBTITLE)"
  nsDialogs::Create 1018
  Pop $0

  ${NSD_CreateLabel} 0 0 100% 20u "$(JAVA_PATH_LABEL)"
  Pop $0

  ${NSD_CreateText} 0 24 100% 16u "$JavaPath"
  Pop $hJavaPathText

  ${NSD_CreateLabel} 0 52 100% 20u "$(JAVA_PORT_LABEL)"
  Pop $0

  ${If} $ApiPort == ""
    StrCpy $ApiPort "29185"
  ${EndIf}
  ${NSD_CreateNumber} 0 76 30% 16u "$ApiPort"
  Pop $hApiPortText

  nsDialogs::Show
FunctionEnd

Function JavaPortLeave
  ${NSD_GetText} $hJavaPathText $0
  StrCpy $JavaPath $0
  ${NSD_GetText} $hApiPortText $0
  StrCpy $ApiPort $0
FunctionEnd

; =============================================================
; PAGE: Startup
; =============================================================
LangString STARTUP_TITLE ${LANG_ENGLISH} "Startup Options"
LangString STARTUP_SUBTITLE ${LANG_ENGLISH} "Choose whether TikTok2MC starts automatically when you log in."
LangString STARTUP_CHECKBOX ${LANG_ENGLISH} "Start TikTok2MC automatically when I log in"

LangString STARTUP_TITLE ${LANG_GERMAN} "Startoptionen"
LangString STARTUP_SUBTITLE ${LANG_GERMAN} "Wählen Sie, ob TikTok2MC automatisch beim Anmelden starten soll."
LangString STARTUP_CHECKBOX ${LANG_GERMAN} "TikTok2MC automatisch beim Anmelden starten"

Function StartupPageCreate
  !insertmacro MUI_HEADER_TEXT "$(STARTUP_TITLE)" "$(STARTUP_SUBTITLE)"
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateCheckBox} 0 0 100% 20u "$(STARTUP_CHECKBOX)"
  Pop $StartupCheckbox
  nsDialogs::Show
FunctionEnd

Function StartupPageLeave
  ${NSD_GetState} $StartupCheckbox $0
  ${If} $0 == 1
    ${If} $InstallType == 1
      ${If} $GuiDefaultMode == 1
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\start.exe"
      ${Else}
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\core\gui.exe"
      ${EndIf}
    ${Else}
      WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\core\gui.exe"
    ${EndIf}
  ${Else}
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME} GUI"
  ${EndIf}
FunctionEnd

; =============================================================
; SECTIONS
; =============================================================

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

  ; ---- Advanced mode: remove unselected components ----
  ${If} $InstallType == 1
    IntOp $0 $AdvancedComponents & 1
    ${If} $0 == 0
      RMDir /r "$INSTDIR\plugins"
    ${EndIf}
    IntOp $0 $AdvancedComponents & 2
    ${If} $0 == 0
      RMDir /r "$INSTDIR\server"
    ${EndIf}
    IntOp $0 $AdvancedComponents & 4
    ${If} $0 == 0
      RMDir /r "$INSTDIR\docs"
    ${EndIf}

    ; Write Java path to config.yaml (append — last value wins in YAML)
    ${If} $JavaPath != ""
      FileOpen $0 "$INSTDIR\config\config.yaml" a
      FileSeek $0 0 END
      FileWrite $0 "$\r$\n"
      FileWrite $0 "# Java path (set by installer)$\r$\n"
      FileWrite $0 'java:$\r$\n'
      FileWrite $0 '  path: "$JavaPath"$\r$\n'
      FileClose $0
    ${EndIf}

    ; Write API port to config.yaml
    FileOpen $0 "$INSTDIR\config\config.yaml" a
    FileSeek $0 0 END
    FileWrite $0 "$\r$\n"
    FileWrite $0 "# API server port (set by installer)$\r$\n"
    FileWrite $0 'api:$\r$\n'
    FileWrite $0 "  port: $ApiPort$\r$\n"
    FileClose $0
  ${EndIf}

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry: uninstall info
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\core\gui.exe,0"
  WriteRegStr HKLM "${PRODUCT_UNINSTALL_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegDword HKLM "${PRODUCT_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDword HKLM "${PRODUCT_UNINSTALL_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDword HKLM "${PRODUCT_UNINSTALL_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Desktop Shortcut" SEC_DESKTOP
  ; Choose target based on InstallType and GuiDefaultMode
  ${If} $InstallType == 0
    ; Basic: always gui.exe
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\core\gui.exe" "" "$INSTDIR\core\gui.exe" 0
  ${Else}
    ${If} $GuiDefaultMode == 1
      CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\start.exe" "" "$INSTDIR\start.exe" 0
    ${Else}
      CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\core\gui.exe" "" "$INSTDIR\core\gui.exe" 0
    ${EndIf}
  ${EndIf}
SectionEnd

Section "Start Menu Shortcut" SEC_STARTMENU
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  ; Main shortcut respects GUI mode
  ${If} $InstallType == 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\TikTok2MC.lnk" "$INSTDIR\core\gui.exe" "" "$INSTDIR\core\gui.exe" 0
  ${Else}
    ${If} $GuiDefaultMode == 1
      CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\TikTok2MC.lnk" "$INSTDIR\start.exe" "" "$INSTDIR\start.exe" 0
    ${Else}
      CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\TikTok2MC.lnk" "$INSTDIR\core\gui.exe" "" "$INSTDIR\core\gui.exe" 0
    ${EndIf}
  ${EndIf}
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Start Full System.lnk" "$INSTDIR\start.exe" "" "$INSTDIR\start.exe" 0
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

  ; Remove startup entries
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME} GUI"

  ; Remove all installed files
  RMDir /r "$INSTDIR"

  ; Remove uninstall registry key
  DeleteRegKey HKLM "${PRODUCT_UNINSTALL_KEY}"
SectionEnd
