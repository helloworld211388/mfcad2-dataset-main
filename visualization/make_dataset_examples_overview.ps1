param(
    [string]$SourceDir = ".\dataset_examples_png",
    [string]$OutputPath = ".\Dataset_Examples_6x3.png",
    [string]$SelectionJson = ""
)

Add-Type -AssemblyName System.Drawing

$fullOutputPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$outputDir = Split-Path -Parent $fullOutputPath
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

$sourceDirFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $SourceDir))
if (-not (Test-Path $sourceDirFull)) {
    throw "Source directory not found: $sourceDirFull"
}

if (-not [string]::IsNullOrWhiteSpace($SelectionJson)) {
    $selectionJsonFull = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $SelectionJson))
    if (-not (Test-Path $selectionJsonFull)) {
        throw "Selection JSON not found: $selectionJsonFull"
    }

    $selectedItems = Get-Content -LiteralPath $selectionJsonFull -Raw | ConvertFrom-Json
    $pngFiles = @()
    foreach ($item in $selectedItems) {
        $pngName = [System.IO.Path]::GetFileNameWithoutExtension($item.name) + ".png"
        $pngPath = Join-Path $sourceDirFull $pngName
        if (-not (Test-Path $pngPath)) {
            throw "Selected PNG missing: $pngPath"
        }
        $pngFiles += Get-Item -LiteralPath $pngPath
    }
} else {
    $pngFiles = Get-ChildItem -LiteralPath $sourceDirFull -Filter *.png | Sort-Object @{Expression = {
        if ($_.BaseName -as [int] -ne $null -and $_.BaseName -match '^\d+$') { [int]$_.BaseName } else { [int]::MaxValue }
    }}, Name | Select-Object -First 18
}

if ($pngFiles.Count -lt 18) {
    throw "Need 18 PNG files in $sourceDirFull, found $($pngFiles.Count)."
}

$columns = 6
$rows = 3
$cellWidth = 440
$cellHeight = 300
$imageWidth = 400
$imageHeight = 260
$margin = 18
$canvasWidth = ($columns * $cellWidth) + (($columns + 1) * $margin)
$canvasHeight = ($rows * $cellHeight) + (($rows + 1) * $margin)

$bitmap = New-Object System.Drawing.Bitmap($canvasWidth, $canvasHeight)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.Clear([System.Drawing.Color]::White)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

for ($index = 0; $index -lt $pngFiles.Count; $index++) {
    $png = $pngFiles[$index]
    $col = $index % $columns
    $row = [math]::Floor($index / $columns)
    $cellX = $margin + ($col * ($cellWidth + $margin))
    $cellY = $margin + ($row * ($cellHeight + $margin))

    $source = [System.Drawing.Image]::FromFile($png.FullName)
    try {
        $scale = [math]::Min($imageWidth / $source.Width, $imageHeight / $source.Height)
        $drawWidth = [int]([math]::Round($source.Width * $scale))
        $drawHeight = [int]([math]::Round($source.Height * $scale))
        $drawX = $cellX + [int](($cellWidth - $drawWidth) / 2)
        $drawY = $cellY + [int](($cellHeight - $drawHeight) / 2)
        $graphics.DrawImage($source, $drawX, $drawY, $drawWidth, $drawHeight)
    }
    finally {
        $source.Dispose()
    }
}

$bitmap.Save($fullOutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()

Write-Output "Saved dataset examples overview: $fullOutputPath"
