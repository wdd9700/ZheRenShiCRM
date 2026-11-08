$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$destination = Join-Path $PSScriptRoot '../build'
[IO.Directory]::CreateDirectory($destination) | Out-Null
$images = @()
foreach ($size in @(16, 24, 32, 48, 64, 128, 256)) {
    $bitmap = [Drawing.Bitmap]::new($size, $size, [Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.ScaleTransform(($size / 40.0), ($size / 40.0))
    $shape = [Drawing.Drawing2D.GraphicsPath]::new()
    $shape.AddArc(1, 1, 18, 18, 180, 90)
    $shape.AddArc(21, 1, 18, 18, 270, 90)
    $shape.AddArc(21, 21, 18, 18, 0, 90)
    $shape.AddArc(1, 21, 18, 18, 90, 90)
    $shape.CloseFigure()
    $background = [Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml('#292D34'))
    $outline = [Drawing.Pen]::new([Drawing.ColorTranslator]::FromHtml('#697380'), 1)
    $graphics.FillPath($background, $shape)
    $graphics.DrawPath($outline, $shape)
    $diamond = [Drawing.Pen]::new([Drawing.ColorTranslator]::FromHtml('#E8EAED'), 2)
    $points = [Drawing.PointF[]]@([Drawing.PointF]::new(20,7), [Drawing.PointF]::new(31,20), [Drawing.PointF]::new(20,31), [Drawing.PointF]::new(9,20))
    $graphics.DrawPolygon($diamond, $points)
    $colors = @('#67D4B0', '#7EB7ED', '#E1BC70')
    for ($i = 0; $i -lt 3; $i++) {
        $brush = [Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml($colors[$i]))
        $graphics.FillEllipse($brush, [single](12.5 + 6 * $i), [single]32.5, [single]3, [single]3)
        $brush.Dispose()
    }
    $stream = [IO.MemoryStream]::new()
    $bitmap.Save($stream, [Drawing.Imaging.ImageFormat]::Png)
    $images += ,@{ Size = $size; Bytes = $stream.ToArray() }
    if ($size -eq 256) { [IO.File]::WriteAllBytes((Join-Path $destination 'icon-preview.png'), $stream.ToArray()) }
    $stream.Dispose(); $diamond.Dispose(); $outline.Dispose(); $background.Dispose(); $shape.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
}
$ico = [IO.MemoryStream]::new()
$writer = [IO.BinaryWriter]::new($ico)
$writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$images.Count)
$offset = 6 + 16 * $images.Count
foreach ($image in $images) {
    $dimension = if ($image.Size -eq 256) { 0 } else { $image.Size }
    $writer.Write([byte]$dimension); $writer.Write([byte]$dimension); $writer.Write([byte]0); $writer.Write([byte]0)
    $writer.Write([uint16]1); $writer.Write([uint16]32); $writer.Write([uint32]$image.Bytes.Length); $writer.Write([uint32]$offset)
    $offset += $image.Bytes.Length
}
foreach ($image in $images) { $writer.Write([byte[]]$image.Bytes) }
$writer.Flush()
[IO.File]::WriteAllBytes((Join-Path $destination 'icon.ico'), $ico.ToArray())
$writer.Dispose(); $ico.Dispose()
