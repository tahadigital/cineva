import AppKit
import CoreGraphics
import Foundation

// Mavie Brand Gradient: #7C3AED -> #3B82F6 -> #06B6D4

private func srgbColor(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1.0) -> CGColor {
    let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
    return CGColor(colorSpace: cs, components: [r / 255.0, g / 255.0, b / 255.0, a])!
}

private func renderMavieIconPNG(pixelSize: Int, macOSGrid: Bool) throws -> Data {
    let s = CGFloat(pixelSize)
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: pixelSize,
        pixelsHigh: pixelSize,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: pixelSize * 4,
        bitsPerPixel: 32
    ) else {
        throw NSError(domain: "MavieIcon", code: 1, userInfo: [NSLocalizedDescriptionKey: "Bitmap oluşturulamadı"])
    }
    rep.size = NSSize(width: pixelSize, height: pixelSize)

    guard let nsCtx = NSGraphicsContext(bitmapImageRep: rep) else {
        throw NSError(domain: "MavieIcon", code: 2, userInfo: [NSLocalizedDescriptionKey: "GraphicsContext oluşturulamadı"])
    }

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = nsCtx
    let ctx = nsCtx.cgContext
    ctx.setAllowsAntialiasing(true)
    ctx.setShouldAntialias(true)
    ctx.interpolationQuality = .high

    let fullRect = CGRect(x: 0, y: 0, width: s, height: s)
    ctx.clear(fullRect)

    let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
    let bgGradient = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(20, 24, 43), srgbColor(8, 11, 20)] as CFArray,
        locations: [0.0, 1.0]
    )!
    let glowGradient = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237, 0.22), srgbColor(6, 182, 212, 0.06), srgbColor(8, 11, 20, 0.0)] as CFArray,
        locations: [0.0, 0.45, 1.0]
    )!
    let ringGradient = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237), srgbColor(59, 130, 246), srgbColor(6, 182, 212)] as CFArray,
        locations: [0.0, 0.52, 1.0]
    )!

    let contentRect: CGRect
    if macOSGrid {
        // Apple macOS HIG 824x824 squircle grid centered on 1024x1024 canvas
        let sqSize = s * (824.0 / 1024.0)
        let inset = (s - sqSize) / 2.0
        contentRect = CGRect(x: inset, y: inset, width: sqSize, height: sqSize)
        let cornerRadius = sqSize * (185.4 / 824.0)
        let squirclePath = CGPath(roundedRect: contentRect, cornerWidth: cornerRadius, cornerHeight: cornerRadius, transform: nil)

        // Subtle ambient drop shadow under squircle (CG Y-up: negative y offset is downward)
        ctx.saveGState()
        ctx.setShadow(
            offset: CGSize(width: 0, height: -s * (14.0 / 1024.0)),
            blur: s * (24.0 / 1024.0),
            color: srgbColor(0, 0, 0, 0.45)
        )
        ctx.addPath(squirclePath)
        ctx.setFillColor(srgbColor(14, 18, 34))
        ctx.fillPath()
        ctx.restoreGState()

        ctx.saveGState()
        ctx.addPath(squirclePath)
        ctx.clip()

        ctx.drawLinearGradient(
            bgGradient,
            start: CGPoint(x: contentRect.minX, y: contentRect.maxY),
            end: CGPoint(x: contentRect.maxX, y: contentRect.minY),
            options: []
        )
        ctx.drawRadialGradient(
            glowGradient,
            startCenter: CGPoint(x: contentRect.minX + sqSize * 0.25, y: contentRect.maxY - sqSize * 0.22),
            startRadius: 0,
            endCenter: CGPoint(x: contentRect.midX, y: contentRect.midY),
            endRadius: sqSize * 0.78,
            options: []
        )

        // Inner hairline border (#22D3EE @ 0.16)
        let borderInset = max(0.75, s * (4.0 / 1024.0))
        let innerRect = contentRect.insetBy(dx: borderInset, dy: borderInset)
        let innerCorner = max(2.0, cornerRadius - borderInset)
        let innerPath = CGPath(roundedRect: innerRect, cornerWidth: innerCorner, cornerHeight: innerCorner, transform: nil)
        ctx.addPath(innerPath)
        ctx.setStrokeColor(srgbColor(34, 211, 238, 0.16))
        ctx.setLineWidth(max(0.75, s * (6.0 / 1024.0)))
        ctx.strokePath()
    } else {
        // Full-bleed opaque 1024x1024 iOS AppIcon (alpha = 255 everywhere)
        contentRect = fullRect
        ctx.saveGState()
        ctx.setFillColor(srgbColor(8, 11, 20))
        ctx.fill(fullRect)
        ctx.drawLinearGradient(
            bgGradient,
            start: CGPoint(x: 0, y: s),
            end: CGPoint(x: s, y: 0),
            options: []
        )
        ctx.drawRadialGradient(
            glowGradient,
            startCenter: CGPoint(x: s * 0.25, y: s * 0.78),
            startRadius: 0,
            endCenter: CGPoint(x: s * 0.5, y: s * 0.5),
            endRadius: s * 0.78,
            options: []
        )
    }

    // Canonical 120x120 Mavie Mark centered in contentRect
    let markScale = macOSGrid
        ? (contentRect.width * (124.0 / 192.0)) / 120.0
        : (s * 0.66) / 120.0
    let cx = contentRect.midX
    let cy = contentRect.midY

    // 1. Open C-arc: radius 38.42, opening on the right (+/-38.66 deg)
    let arcRadius = 38.42 * markScale
    let openAngle = CGFloat(38.66 * Double.pi / 180.0)
    let arcPath = CGMutablePath()
    arcPath.addArc(
        center: CGPoint(x: cx, y: cy),
        radius: arcRadius,
        startAngle: openAngle,
        endAngle: -openAngle,
        clockwise: false
    )
    let strokedArc = arcPath.copy(
        strokingWithWidth: max(1.5, 16.0 * markScale),
        lineCap: .round,
        lineJoin: .round,
        miterLimit: 10
    )
    ctx.saveGState()
    ctx.addPath(strokedArc)
    ctx.clip()
    let gradSpan = 52.0 * markScale
    ctx.drawLinearGradient(
        ringGradient,
        start: CGPoint(x: cx - gradSpan, y: cy + gradSpan),
        end: CGPoint(x: cx + gradSpan, y: cy - gradSpan),
        options: [.drawsBeforeStartLocation, .drawsAfterEndLocation]
    )
    ctx.restoreGState()

    // 2. Rounded white play triangle: (52,43) -> (83,60) -> (52,77) relative to (60,60)
    let triPath = CGMutablePath()
    triPath.move(to: CGPoint(x: cx - 8.0 * markScale, y: cy + 17.0 * markScale))
    triPath.addLine(to: CGPoint(x: cx + 23.0 * markScale, y: cy))
    triPath.addLine(to: CGPoint(x: cx - 8.0 * markScale, y: cy - 17.0 * markScale))
    triPath.closeSubpath()

    ctx.addPath(triPath)
    ctx.setFillColor(srgbColor(255, 255, 255))
    ctx.fillPath()

    ctx.addPath(triPath)
    ctx.setStrokeColor(srgbColor(255, 255, 255))
    ctx.setLineWidth(max(0.8, 4.0 * markScale))
    ctx.setLineJoin(.round)
    ctx.setLineCap(.round)
    ctx.strokePath()

    // 3. Cyan dot (#22D3EE) at (92, 60) -> (+32, 0)
    let dotRadius = max(0.8, 5.2 * markScale)
    let dotRect = CGRect(
        x: cx + 32.0 * markScale - dotRadius,
        y: cy - dotRadius,
        width: dotRadius * 2.0,
        height: dotRadius * 2.0
    )
    ctx.setFillColor(srgbColor(34, 211, 238))
    ctx.fillEllipse(in: dotRect)

    ctx.restoreGState()
    NSGraphicsContext.restoreGraphicsState()

    guard let pngData = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "MavieIcon", code: 3, userInfo: [NSLocalizedDescriptionKey: "PNG kodlanamadı"])
    }
    return pngData
}

let args = CommandLine.arguments
guard args.count >= 4 else {
    fputs("Usage: generate_app_icons.swift <iconset_dir> <macos_xcassets_dir> <ios_icon_path>\n", stderr)
    exit(2)
}

let iconsetDir = URL(fileURLWithPath: args[1], isDirectory: true)
let macAssetsDir = URL(fileURLWithPath: args[2], isDirectory: true)
let iosIconURL = URL(fileURLWithPath: args[3], isDirectory: false)

let fm = FileManager.default
try fm.createDirectory(at: iconsetDir, withIntermediateDirectories: true)
try fm.createDirectory(at: macAssetsDir, withIntermediateDirectories: true)
try fm.createDirectory(at: iosIconURL.deletingLastPathComponent(), withIntermediateDirectories: true)

let specs: [(filename: String, pixels: Int)] = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

var renderedBySize: [Int: Data] = [:]
for spec in specs {
    let data: Data
    if let cached = renderedBySize[spec.pixels] {
        data = cached
    } else {
        data = try renderMavieIconPNG(pixelSize: spec.pixels, macOSGrid: true)
        renderedBySize[spec.pixels] = data
    }
    try data.write(to: iconsetDir.appendingPathComponent(spec.filename), options: [.atomic])
    try data.write(to: macAssetsDir.appendingPathComponent(spec.filename), options: [.atomic])
}

let iosData = try renderMavieIconPNG(pixelSize: 1024, macOSGrid: false)
try iosData.write(to: iosIconURL, options: [.atomic])
print("Generated \(specs.count) macOS icons and 1024x1024 iOS AppIcon.")
