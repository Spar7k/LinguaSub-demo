!macro LINGUASUB_RUN_MODEL_CLEANUP configPath modelDir
  ${If} ${FileExists} "$INSTDIR\linguasub-backend.exe"
    DetailPrint "LinguaSub is safely removing its managed speech models from ${modelDir}"
    nsExec::ExecToLog `"$INSTDIR\linguasub-backend.exe" --cleanup-models --config-path "${configPath}" --model-dir "${modelDir}"`
    Pop $0
    ${If} $0 != 0
      DetailPrint "LinguaSub skipped automatic model cleanup for ${modelDir} because the safe cleanup command did not complete successfully."
    ${EndIf}
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Add a desktop shortcut after Tauri finishes its built-in install steps.
  ; The shortcut icon comes from the installed EXE, so it stays in sync
  ; with the current application icon embedded by Tauri.
  CreateShortCut "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe" "" "$INSTDIR\${MAINBINARYNAME}.exe" 0
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; Updates should keep the user's downloaded models. Only full uninstall
  ; runs the safe LinguaSub-managed model cleanup flow.
  ${If} $UpdateMode <> 1
    !insertmacro LINGUASUB_RUN_MODEL_CLEANUP "$APPDATA\${BUNDLEID}\app-config.json" "$APPDATA\${BUNDLEID}\speech-models"
    ; Older builds may have used the product-name app data folder directly.
    ; This second pass is still safe because the backend only deletes marked
    ; and recorded LinguaSub-owned model directories.
    !insertmacro LINGUASUB_RUN_MODEL_CLEANUP "$APPDATA\${PRODUCTNAME}\app-config.json" "$APPDATA\${PRODUCTNAME}\speech-models"
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Remove the desktop shortcut during uninstall if it still exists.
  Delete "$DESKTOP\${PRODUCTNAME}.lnk"
!macroend
