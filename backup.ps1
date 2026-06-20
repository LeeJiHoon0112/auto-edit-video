# ============================================================
#  BACKUP AUTO EDIT VIDEO
#  Gom cac file SONG CON (khong co tren GitHub) thanh 1 file zip
#  ten "Backup AutoEditvideo.zip" tren Desktop de upload len Drive.
#
#  Cach chay:  double-click backup.bat
#         hoac:  chuot phai backup.ps1 > Run with PowerShell
# ============================================================

$ErrorActionPreference = 'Stop'

# --- Thu muc du an = thu muc chua script nay ---
$Project = $PSScriptRoot
if (-not $Project) { $Project = (Get-Location).Path }

# --- Noi luu file zip: Desktop ---
$Desktop = [Environment]::GetFolderPath('Desktop')
$ZipName = 'Backup AutoEditvideo'
$ZipPath = Join-Path $Desktop ($ZipName + '.zip')

# --- Danh sach file can backup (chi cai KHONG co tren GitHub) ---
$Critical = @(
    'config.local.json',   # keys API + style profiles + cau hinh  <-- QUAN TRONG NHAT
    'Context.md',          # tri nho du an
    'COWORK_CONTEXT.md',   # tai lieu Cowork (chua push)
    'access.json',         # hash mat khau hien tai (giu cho chac)
    'session.local.json',  # token dang nhap may (khong bat buoc)
    'scenes.csv',
    'veo_prompts.txt',
    'image_prompts.txt',
    'motion_prompts.txt'
)

Write-Host ''
Write-Host '=================================================='
Write-Host '   BACKUP AUTO EDIT VIDEO'
Write-Host '=================================================='
Write-Host ''

# --- Thu muc tam de gom file ---
$Stage = Join-Path $env:TEMP ('AEV_backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

$copied = @()
$missing = @()
foreach ($f in $Critical) {
    $src = Join-Path $Project $f
    if (Test-Path $src) {
        Copy-Item $src -Destination $Stage -Force
        $kb = [math]::Round((Get-Item $src).Length / 1KB, 1)
        Write-Host ('  [+] ' + $f + '  (' + $kb + ' KB)')
        $copied += $f
    } else {
        Write-Host ('  [ ] ' + $f + '   -- khong co, bo qua')
        $missing += $f
    }
}

# --- Tao file huong dan khoi phuc kem trong zip ---
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
$guide = @"
HUONG DAN KHOI PHUC - Auto Edit Video
=====================================
Ngay backup: $stamp

CAC BUOC SAU KHI CAI LAI WINDOWS:

1. Cai git roi clone code (code da an toan tren GitHub):
   git clone https://github.com/LeeJiHoon0112/auto-edit-video.git

2. Chay  install.bat  -> tu cai Python + FFmpeg.

3. Chep cac file trong zip nay vao thu muc goc "Auto Edit Video":
   - config.local.json  (BAT BUOC - keys API + style profiles)
   - Context.md, COWORK_CONTEXT.md
   - scenes.csv / *_prompts.txt  (cua video dang lam, neu con can)

4. Tao Personal Access Token MOI tren GitHub de push (revoke token cu).

5. Chay  run.bat  -> dang nhap (mat khau Hoangkha@1) -> dev tiep.

LUU Y QUAN TRONG:
 - Zip nay KHONG chua MEDIA (clip Veo .mp4, voice.wav, output/...) vi qua nang.
   Hay backup media RIENG sang o cung ngoai / Google Drive.
 - File config.local.json chua API KEYS -> de Drive o che do RIENG TU,
   khong chia se link cong khai.
"@
$guidePath = Join-Path $Stage 'HUONG DAN KHOI PHUC.txt'
$guide | Out-File -FilePath $guidePath -Encoding utf8

# --- Nen thanh zip ---
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $ZipPath -Force

# --- Don thu muc tam ---
Remove-Item $Stage -Recurse -Force

$zipKb = [math]::Round((Get-Item $ZipPath).Length / 1KB, 1)
Write-Host ''
Write-Host ('  Da gom ' + $copied.Count + ' file vao zip.')
if ($missing.Count -gt 0) {
    Write-Host ('  (Bo qua ' + $missing.Count + ' file khong ton tai - binh thuong.)')
}
Write-Host ''
Write-Host '  >> ZIP DA TAO XONG:'
Write-Host ('     ' + $ZipPath)
Write-Host ('     (' + $zipKb + ' KB)')
Write-Host ''
Write-Host '  -> Bay gio upload file nay len Google Drive (de che do rieng tu).'
Write-Host '  -> Dung quen backup MEDIA (clip Veo) rieng - khong nam trong zip nay.'
Write-Host ''
