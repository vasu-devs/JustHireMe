!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Stopping running JustHireMe processes before upgrade..."
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /IM justhireme.exe /T /F'
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /IM jhm-sidecar-next.exe /T /F'
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /IM backend.exe /T /F'
  Sleep 2000

  ClearErrors
  Delete "$INSTDIR\jhm-sidecar-next.exe"
  Delete "$INSTDIR\jhm-sidecar-next*.exe"
  Delete "$INSTDIR\backend.exe"
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\resources\sidecar-internal"
  RMDir /r "$INSTDIR\resources\backend\_internal"
  DetailPrint "Retrying bundled backend cleanup..."
  Sleep 1500
  ClearErrors
  Delete "$INSTDIR\jhm-sidecar-next.exe"
  Delete "$INSTDIR\jhm-sidecar-next*.exe"
  Delete "$INSTDIR\backend.exe"
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\resources\sidecar-internal"
  RMDir /r "$INSTDIR\resources\backend\_internal"
  Sleep 2500
  ClearErrors
  Delete "$INSTDIR\jhm-sidecar-next.exe"
  Delete "$INSTDIR\jhm-sidecar-next*.exe"
  Delete "$INSTDIR\backend.exe"
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\resources\sidecar-internal"
  RMDir /r "$INSTDIR\resources\backend\_internal"
  DetailPrint "Bundled backend cleanup complete."
!macroend

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Repairing JustHireMe Windows install metadata..."
  SetShellVarContext current

  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayName" "${PRODUCTNAME}"
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr SHCTX "${UNINSTKEY}" "Publisher" "${MANUFACTURER}"
  WriteRegStr SHCTX "${UNINSTKEY}" "InstallLocation" "$\"$INSTDIR$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayIcon" "$\"$INSTDIR\${MAINBINARYNAME}.exe$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "QuietUninstallString" "$\"$INSTDIR\uninstall.exe$\" /S"

  IfFileExists "$INSTDIR\${MAINBINARYNAME}.exe" 0 jhm_postinstall_skip_shortcuts
  SetOutPath "$INSTDIR"

  CreateDirectory "$SMPROGRAMS"
  CreateShortCut "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe" "" "$INSTDIR\${MAINBINARYNAME}.exe" 0 SW_SHOWNORMAL "" "${PRODUCTNAME}"

  IfFileExists "$DESKTOP\${PRODUCTNAME}.lnk" 0 +2
    CreateShortCut "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe" "" "$INSTDIR\${MAINBINARYNAME}.exe" 0 SW_SHOWNORMAL "" "${PRODUCTNAME}"

  IfFileExists "$APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\${PRODUCTNAME}.lnk" 0 +2
    CreateShortCut "$APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe" "" "$INSTDIR\${MAINBINARYNAME}.exe" 0 SW_SHOWNORMAL "" "${PRODUCTNAME}"

  Goto jhm_postinstall_done

  jhm_postinstall_skip_shortcuts:
    DetailPrint "Skipping shortcut repair because $INSTDIR\${MAINBINARYNAME}.exe does not exist."

  jhm_postinstall_done:
  DetailPrint "JustHireMe Windows install metadata repaired."
!macroend
