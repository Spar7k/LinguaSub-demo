$ErrorActionPreference = 'Stop'

$root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')
$ffmpegPath = Join-Path $root 'src-tauri\resources\runtime\ffmpeg\ffmpeg.exe'
$backendBinary = Join-Path $root '.pyinstaller\dist\linguasub-backend.exe'
$tauriBinary = Join-Path $root 'src-tauri\binaries\linguasub-backend-x86_64-pc-windows-msvc.exe'

if (!(Test-Path -LiteralPath $ffmpegPath)) {
  throw "Bundled FFmpeg was not found at '$ffmpegPath'. Place ffmpeg.exe there before running npm.cmd run tauri:build."
}

Push-Location $root
try {
  & py -3 -m PyInstaller --noconfirm --distpath .pyinstaller/dist --workpath .pyinstaller/build linguasub-backend.spec
  if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller backend build failed.'
  }

  if (!(Test-Path -LiteralPath $backendBinary)) {
    throw "Expected bundled backend executable was not created at '$backendBinary'."
  }

  Copy-Item -LiteralPath $backendBinary -Destination $tauriBinary -Force
}
finally {
  Pop-Location
}
