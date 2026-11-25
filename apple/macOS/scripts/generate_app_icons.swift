import AppKit
import CoreGraphics
import CoreText
import Foundation

// Mavie Flagship Brand Emblem (M + concentric bottom-left 'o' lens ring)
// Palette: Obsidian Glass (#12172C -> #0B0E1A -> #05070E) + Luminous Prism (#7C3AED -> #3B82F6 -> #06B6D4 / #22D3EE)

private enum IconStyle {
    case macOSGrid     // Apple macOS HIG 824/1024 squircle + subtle ambient drop shadow
    case iOSFullBleed  // Full-bleed opaque 1024x1024 (alpha = 255 everywhere)
    case webSquircle   // Full-canvas rounded squircle (Windows .ico & Android legacy mipmaps)
}

private func srgbColor(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1.0) -> CGColor {
    let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
    return CGColor(colorSpace: cs, components: [r / 255.0, g / 255.0, b / 255.0, a])!
}

private func buildMPath(_ pt: (CGFloat, CGFloat) -> CGPoint) -> CGPath {
    let p = CGMutablePath()
    p.move(to: pt(23.50, 40.00))
    p.addCurve(to: pt(34.50, 28.50), control1: pt(23.50, 32.50), control2: pt(27.20, 29.20))
    p.addCurve(to: pt(95.50, 29.00), control1: pt(56.50, 26.20), control2: pt(77.50, 26.50))
    p.addCurve(to: pt(105.40, 38.00), control1: pt(101.00, 29.80), control2: pt(103.80, 32.80))
    p.addLine(to: pt(129.00, 128.50))
    p.addLine(to: pt(152.60, 38.00))
    p.addCurve(to: pt(162.50, 29.00), control1: pt(154.20, 32.80), control2: pt(157.00, 29.80))
    p.addCurve(to: pt(223.50, 28.50), control1: pt(180.50, 26.50), control2: pt(201.50, 26.20))
    p.addCurve(to: pt(234.50, 40.00), control1: pt(230.80, 29.20), control2: pt(234.50, 32.50))
    p.addLine(to: pt(234.50, 207.50))
    p.addCurve(to: pt(216.00, 224.50), control1: pt(234.50, 218.50), control2: pt(227.50, 224.50))
    p.addLine(to: pt(195.50, 224.50))
    p.addCurve(to: pt(184.50, 213.00), control1: pt(188.50, 224.50), control2: pt(184.50, 220.20))
    p.addLine(to: pt(184.50, 110.00))
    p.addLine(to: pt(180.00, 110.00))
    p.addLine(to: pt(150.50, 214.00))
    p.addCurve(to: pt(136.00, 224.50), control1: pt(148.50, 221.00), control2: pt(143.50, 224.50))
    p.addLine(to: pt(123.50, 224.50))
    // G1-continuous junction from baseline into vertical trunk flank and concentric arch around 'o'
    p.addCurve(to: pt(107.50, 208.50), control1: pt(113.00, 224.50), control2: pt(107.50, 219.00))
    p.addLine(to: pt(107.50, 181.50))
    p.addCurve(to: pt(80.18, 131.61), control1: pt(107.50, 160.61), control2: pt(96.99, 141.42))
    p.addCurve(to: pt(27.20, 134.66), control1: pt(63.36, 121.81), control2: pt(42.99, 122.98))
    p.addCurve(to: pt(23.50, 130.00), control1: pt(24.80, 136.44), control2: pt(23.50, 134.60))
    p.closeSubpath()
    return p
}

private func appendEllipse(
    to path: CGMutablePath,
    cx: CGFloat,
    cy: CGFloat,
    rx: CGFloat,
    ry: CGFloat,
    ccw: Bool,
    pt: (CGFloat, CGFloat) -> CGPoint
) {
    let k: CGFloat = 0.5522847498
    let kx = rx * k
    let ky = ry * k
    path.move(to: pt(cx, cy - ry))
    if !ccw {
        path.addCurve(to: pt(cx + rx, cy), control1: pt(cx + kx, cy - ry), control2: pt(cx + rx, cy - ky))
        path.addCurve(to: pt(cx, cy + ry), control1: pt(cx + rx, cy + ky), control2: pt(cx + kx, cy + ry))
        path.addCurve(to: pt(cx - rx, cy), control1: pt(cx - kx, cy + ry), control2: pt(cx - rx, cy + ky))
        path.addCurve(to: pt(cx, cy - ry), control1: pt(cx - rx, cy - ky), control2: pt(cx - kx, cy - ry))
    } else {
        path.addCurve(to: pt(cx - rx, cy), control1: pt(cx - kx, cy - ry), control2: pt(cx - rx, cy - ky))
        path.addCurve(to: pt(cx, cy + ry), control1: pt(cx - rx, cy + ky), control2: pt(cx - kx, cy + ry))
        path.addCurve(to: pt(cx + rx, cy), control1: pt(cx + kx, cy + ry), control2: pt(cx + rx, cy + ky))
        path.addCurve(to: pt(cx, cy - ry), control1: pt(cx + rx, cy - ky), control2: pt(cx + kx, cy - ry))
    }
    path.closeSubpath()
}

private func buildEllipsePath(
    cx: CGFloat,
    cy: CGFloat,
    rx: CGFloat,
    ry: CGFloat,
    pt: (CGFloat, CGFloat) -> CGPoint
) -> CGPath {
    let p = CGMutablePath()
    appendEllipse(to: p, cx: cx, cy: cy, rx: rx, ry: ry, ccw: false, pt: pt)
    return p
}

private func strokeWithGradient(
    ctx: CGContext,
    path: CGPath,
    lineWidth: CGFloat,
    gradient: CGGradient,
    start: CGPoint,
    end: CGPoint
) {
    let stroked = path.copy(
        strokingWithWidth: lineWidth,
        lineCap: .round,
        lineJoin: .round,
        miterLimit: 10
    )
    ctx.saveGState()
    ctx.addPath(stroked)
    ctx.clip()
    ctx.drawLinearGradient(
        gradient,
        start: start,
        end: end,
        options: [.drawsBeforeStartLocation, .drawsAfterEndLocation]
    )
    ctx.restoreGState()
}

private func renderMavieIconPNG(pixelSize: Int, style: IconStyle) throws -> Data {
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
        throw NSError(domain: "MavieIcon", code: 1, userInfo: [NSLocalizedDescriptionKey: "Bitmap olusturulamadi"])
    }
    rep.size = NSSize(width: pixelSize, height: pixelSize)

    guard let nsCtx = NSGraphicsContext(bitmapImageRep: rep) else {
        throw NSError(domain: "MavieIcon", code: 2, userInfo: [NSLocalizedDescriptionKey: "GraphicsContext olusturulamadi"])
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

    let cardBgGradient = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(18, 23, 44), srgbColor(11, 14, 26), srgbColor(5, 7, 14)] as CFArray,
        locations: [0.0, 0.48, 1.0]
    )!
    let violetAura = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237, 0.30), srgbColor(59, 130, 246, 0.10), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.55, 1.0]
    )!
    let cyanAura = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(6, 182, 212, 0.21), srgbColor(59, 130, 246, 0.08), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.52, 1.0]
    )!
    let glassSheen = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(255, 255, 255, 0.12), srgbColor(255, 255, 255, 0.025), srgbColor(255, 255, 255, 0.0)] as CFArray,
        locations: [0.0, 0.38, 1.0]
    )!
    let cardBorderGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(255, 255, 255, 0.26),
            srgbColor(124, 58, 237, 0.24),
            srgbColor(59, 130, 246, 0.20),
            srgbColor(6, 182, 212, 0.30),
        ] as CFArray,
        locations: [0.0, 0.35, 0.72, 1.0]
    )!
    let topSpecGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(255, 255, 255, 0.0),
            srgbColor(255, 255, 255, 0.30),
            srgbColor(255, 255, 255, 0.42),
            srgbColor(255, 255, 255, 0.30),
            srgbColor(255, 255, 255, 0.0),
        ] as CFArray,
        locations: [0.0, 0.22, 0.50, 0.78, 1.0]
    )!
    let obsidianCore = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(22, 28, 50), srgbColor(9, 13, 24), srgbColor(3, 5, 10)] as CFArray,
        locations: [0.0, 0.42, 1.0]
    )!
    let mRimGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(124, 58, 237),
            srgbColor(59, 130, 246),
            srgbColor(6, 182, 212),
            srgbColor(59, 130, 246),
            srgbColor(124, 58, 237),
        ] as CFArray,
        locations: [0.0, 0.22, 0.50, 0.78, 1.0]
    )!
    let oRimGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(124, 58, 237),
            srgbColor(6, 182, 212),
            srgbColor(59, 130, 246),
        ] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!
    let oInnerRimGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(6, 182, 212),
            srgbColor(59, 130, 246),
            srgbColor(124, 58, 237),
        ] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!

    let contentRect: CGRect
    switch style {
    case .macOSGrid:
        let sqSize = s * (824.0 / 1024.0)
        let inset = (s - sqSize) / 2.0
        contentRect = CGRect(x: inset, y: inset, width: sqSize, height: sqSize)
        let cornerRadius = sqSize * (185.4 / 824.0)
        let squirclePath = CGPath(roundedRect: contentRect, cornerWidth: cornerRadius, cornerHeight: cornerRadius, transform: nil)

        ctx.saveGState()
        ctx.setShadow(
            offset: CGSize(width: 0, height: -s * (14.0 / 1024.0)),
            blur: s * (24.0 / 1024.0),
            color: srgbColor(0, 0, 0, 0.48)
        )
        ctx.addPath(squirclePath)
        ctx.setFillColor(srgbColor(11, 14, 26))
        ctx.fillPath()
        ctx.restoreGState()

        ctx.saveGState()
        ctx.addPath(squirclePath)
        ctx.clip()

    case .webSquircle:
        let pad = s * (4.0 / 256.0)
        let sqSize = s - pad * 2.0
        contentRect = CGRect(x: pad, y: pad, width: sqSize, height: sqSize)
        let cornerRadius = sqSize * (58.0 / 248.0)
        let squirclePath = CGPath(roundedRect: contentRect, cornerWidth: cornerRadius, cornerHeight: cornerRadius, transform: nil)

        ctx.saveGState()
        ctx.addPath(squirclePath)
        ctx.clip()

    case .iOSFullBleed:
        contentRect = fullRect
        ctx.saveGState()
        ctx.setFillColor(srgbColor(5, 7, 14))
        ctx.fill(fullRect)
    }

    // Backdrop: deep obsidian Liquid Glass + dual violet/cyan ambient auras + top sheen
    ctx.drawLinearGradient(
        cardBgGradient,
        start: CGPoint(x: contentRect.minX + contentRect.width * 0.12, y: contentRect.maxY),
        end: CGPoint(x: contentRect.minX + contentRect.width * 0.88, y: contentRect.minY),
        options: [.drawsBeforeStartLocation, .drawsAfterEndLocation]
    )
    ctx.drawRadialGradient(
        violetAura,
        startCenter: CGPoint(x: contentRect.minX + contentRect.width * 0.24, y: contentRect.maxY - contentRect.height * 0.24),
        startRadius: 0,
        endCenter: CGPoint(x: contentRect.minX + contentRect.width * 0.24, y: contentRect.maxY - contentRect.height * 0.24),
        endRadius: contentRect.width * 0.62,
        options: []
    )
    ctx.drawRadialGradient(
        cyanAura,
        startCenter: CGPoint(x: contentRect.minX + contentRect.width * 0.62, y: contentRect.maxY - contentRect.height * 0.68),
        startRadius: 0,
        endCenter: CGPoint(x: contentRect.minX + contentRect.width * 0.62, y: contentRect.maxY - contentRect.height * 0.68),
        endRadius: contentRect.width * 0.58,
        options: []
    )
    ctx.drawLinearGradient(
        glassSheen,
        start: CGPoint(x: contentRect.minX + contentRect.width * 0.25, y: contentRect.maxY),
        end: CGPoint(x: contentRect.minX + contentRect.width * 0.55, y: contentRect.maxY - contentRect.height * 0.58),
        options: [.drawsBeforeStartLocation, .drawsAfterEndLocation]
    )

    // Prismatic Liquid Glass inner border + faded top specular highlight for squircle styles
    if style == .macOSGrid || style == .webSquircle {
        let cornerRadius = style == .macOSGrid
            ? contentRect.width * (185.4 / 824.0)
            : contentRect.width * (58.0 / 248.0)
        let borderW = max(0.75, contentRect.width * (2.6 / 248.0))
        let borderInset = borderW * 0.5 + max(0.5, contentRect.width * (1.2 / 248.0))
        let innerRect = contentRect.insetBy(dx: borderInset, dy: borderInset)
        let innerCorner = max(2.0, cornerRadius - borderInset)
        let innerPath = CGPath(roundedRect: innerRect, cornerWidth: innerCorner, cornerHeight: innerCorner, transform: nil)
        strokeWithGradient(
            ctx: ctx,
            path: innerPath,
            lineWidth: borderW,
            gradient: cardBorderGradient,
            start: CGPoint(x: innerRect.minX, y: innerRect.maxY),
            end: CGPoint(x: innerRect.maxX, y: innerRect.minY)
        )

        if pixelSize >= 48 {
            let specPath = CGMutablePath()
            let specY = innerRect.maxY - borderW * 0.15
            specPath.move(to: CGPoint(x: innerRect.minX + innerCorner * 0.85, y: specY))
            specPath.addLine(to: CGPoint(x: innerRect.maxX - innerCorner * 0.85, y: specY))
            strokeWithGradient(
                ctx: ctx,
                path: specPath,
                lineWidth: max(0.8, contentRect.width * (1.8 / 248.0)),
                gradient: topSpecGradient,
                start: CGPoint(x: innerRect.minX + innerCorner * 0.85, y: specY),
                end: CGPoint(x: innerRect.maxX - innerCorner * 0.85, y: specY)
            )
        }
    }

    // Emblem coordinate mapping (canonical 256x256 centered optically inside contentRect)
    let emblemFraction: CGFloat
    switch style {
    case .macOSGrid: emblemFraction = 0.82
    case .webSquircle: emblemFraction = 0.83
    case .iOSFullBleed: emblemFraction = 0.78
    }
    let emblemSize = contentRect.width * emblemFraction
    let scale = emblemSize / 256.0
    let ox = contentRect.midX - emblemSize * 0.5
    // Optical vertical centering (+1.5/256 nudge downward in Y-down = slightly lower in Y-up)
    let oy = contentRect.midY - emblemSize * 0.5 - (1.8 * scale)

    let pt: (CGFloat, CGFloat) -> CGPoint = { x, y in
        CGPoint(x: ox + x * scale, y: oy + (256.0 - y) * scale)
    }

    let mPath = buildMPath(pt)
    let oOuterPath = buildEllipsePath(cx: 56.0, cy: 181.5, rx: 35.0, ry: 39.0, pt: pt)
    let oInnerPath = buildEllipsePath(cx: 56.0, cy: 181.5, rx: 13.8, ry: 15.6, pt: pt)
    let oDonutPath = CGMutablePath()
    appendEllipse(to: oDonutPath, cx: 56.0, cy: 181.5, rx: 35.0, ry: 39.0, ccw: false, pt: pt)
    appendEllipse(to: oDonutPath, cx: 56.0, cy: 181.5, rx: 13.8, ry: 15.6, ccw: true, pt: pt)

    // Optical stroke compensation so 16px/24px/32px icons stay unmistakably crisp & luminous
    let opticalBoost: CGFloat
    if pixelSize <= 16 {
        opticalBoost = 1.42
    } else if pixelSize <= 24 {
        opticalBoost = 1.26
    } else if pixelSize <= 32 {
        opticalBoost = 1.15
    } else {
        opticalBoost = 1.0
    }
    let outerStrokeW = max(1.15, 10.2 * scale * opticalBoost)
    let innerStrokeW = max(0.95, 8.8 * scale * opticalBoost)

    let mStart = pt(10.24, 112.64)
    let mEnd = pt(245.76, 143.36)
    let oStart = pt(26.6, 181.5)
    let oEnd = pt(85.4, 181.5)
    let oInStart = pt(56.0, 165.9)
    let oInEnd = pt(56.0, 197.1)

    // Soft ambient prism glow behind the emblem contour (for icons >= 48px)
    if pixelSize >= 48 {
        ctx.saveGState()
        ctx.setAlpha(0.36)
        ctx.beginTransparencyLayer(auxiliaryInfo: nil)
        ctx.setShadow(offset: .zero, blur: max(2.5, 12.5 * scale), color: srgbColor(59, 130, 246, 0.92))
        strokeWithGradient(ctx: ctx, path: mPath, lineWidth: outerStrokeW * 1.22, gradient: mRimGradient, start: mStart, end: mEnd)
        strokeWithGradient(ctx: ctx, path: oOuterPath, lineWidth: outerStrokeW * 1.22, gradient: oRimGradient, start: oStart, end: oEnd)
        ctx.endTransparencyLayer()
        ctx.restoreGState()
    }

    // Obsidian glass sculpted fill for M body
    ctx.saveGState()
    ctx.addPath(mPath)
    ctx.clip()
    ctx.drawLinearGradient(obsidianCore, start: pt(46.0, 26.0), end: pt(210.0, 226.0), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    ctx.restoreGState()

    // Obsidian glass sculpted fill for 'o' lens donut (transparent aperture cutout via evenOdd)
    ctx.saveGState()
    ctx.addPath(oDonutPath)
    ctx.clip(using: .evenOdd)
    ctx.drawLinearGradient(obsidianCore, start: pt(24.0, 142.0), end: pt(88.0, 222.0), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    ctx.restoreGState()

    // Luminous gradient rims
    strokeWithGradient(ctx: ctx, path: mPath, lineWidth: outerStrokeW, gradient: mRimGradient, start: mStart, end: mEnd)
    strokeWithGradient(ctx: ctx, path: oOuterPath, lineWidth: outerStrokeW, gradient: oRimGradient, start: oStart, end: oEnd)
    strokeWithGradient(ctx: ctx, path: oInnerPath, lineWidth: innerStrokeW, gradient: oInnerRimGradient, start: oInStart, end: oInEnd)

    ctx.restoreGState()
    NSGraphicsContext.restoreGraphicsState()

    guard let pngData = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "MavieIcon", code: 3, userInfo: [NSLocalizedDescriptionKey: "PNG kodlanamadi"])
    }
    return pngData
}

private func drawMavieEmblem(
    ctx: CGContext,
    rect: CGRect,
    withBloom: Bool,
    opticalBoost: CGFloat = 1.0
) {
    let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
    let obsidianCore = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(22, 28, 50), srgbColor(9, 13, 24), srgbColor(3, 5, 10)] as CFArray,
        locations: [0.0, 0.42, 1.0]
    )!
    let mRimGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(124, 58, 237),
            srgbColor(59, 130, 246),
            srgbColor(6, 182, 212),
            srgbColor(59, 130, 246),
            srgbColor(124, 58, 237),
        ] as CFArray,
        locations: [0.0, 0.22, 0.50, 0.78, 1.0]
    )!
    let oRimGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(124, 58, 237),
            srgbColor(6, 182, 212),
            srgbColor(59, 130, 246),
        ] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!
    let oInnerRimGradient = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(6, 182, 212),
            srgbColor(59, 130, 246),
            srgbColor(124, 58, 237),
        ] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!

    let emblemSize = min(rect.width, rect.height)
    let scale = emblemSize / 256.0
    let ox = rect.midX - emblemSize * 0.5
    let oy = rect.midY - emblemSize * 0.5 - (1.8 * scale)

    let pt: (CGFloat, CGFloat) -> CGPoint = { x, y in
        CGPoint(x: ox + x * scale, y: oy + (256.0 - y) * scale)
    }

    let mPath = buildMPath(pt)
    let oOuterPath = buildEllipsePath(cx: 56.0, cy: 181.5, rx: 35.0, ry: 39.0, pt: pt)
    let oInnerPath = buildEllipsePath(cx: 56.0, cy: 181.5, rx: 13.8, ry: 15.6, pt: pt)
    let oDonutPath = CGMutablePath()
    appendEllipse(to: oDonutPath, cx: 56.0, cy: 181.5, rx: 35.0, ry: 39.0, ccw: false, pt: pt)
    appendEllipse(to: oDonutPath, cx: 56.0, cy: 181.5, rx: 13.8, ry: 15.6, ccw: true, pt: pt)

    let outerStrokeW = max(1.15, 10.2 * scale * opticalBoost)
    let innerStrokeW = max(0.95, 8.8 * scale * opticalBoost)

    let mStart = pt(10.24, 112.64)
    let mEnd = pt(245.76, 143.36)
    let oStart = pt(26.6, 181.5)
    let oEnd = pt(85.4, 181.5)
    let oInStart = pt(56.0, 165.9)
    let oInEnd = pt(56.0, 197.1)

    if withBloom {
        ctx.saveGState()
        ctx.setAlpha(0.38)
        ctx.beginTransparencyLayer(auxiliaryInfo: nil)
        ctx.setShadow(offset: .zero, blur: max(2.5, 13.5 * scale), color: srgbColor(59, 130, 246, 0.92))
        strokeWithGradient(ctx: ctx, path: mPath, lineWidth: outerStrokeW * 1.24, gradient: mRimGradient, start: mStart, end: mEnd)
        strokeWithGradient(ctx: ctx, path: oOuterPath, lineWidth: outerStrokeW * 1.24, gradient: oRimGradient, start: oStart, end: oEnd)
        ctx.endTransparencyLayer()
        ctx.restoreGState()
    }

    ctx.saveGState()
    ctx.addPath(mPath)
    ctx.clip()
    ctx.drawLinearGradient(obsidianCore, start: pt(46.0, 26.0), end: pt(210.0, 226.0), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    ctx.restoreGState()

    ctx.saveGState()
    ctx.addPath(oDonutPath)
    ctx.clip(using: .evenOdd)
    ctx.drawLinearGradient(obsidianCore, start: pt(24.0, 142.0), end: pt(88.0, 222.0), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    ctx.restoreGState()

    strokeWithGradient(ctx: ctx, path: mPath, lineWidth: outerStrokeW, gradient: mRimGradient, start: mStart, end: mEnd)
    strokeWithGradient(ctx: ctx, path: oOuterPath, lineWidth: outerStrokeW, gradient: oRimGradient, start: oStart, end: oEnd)
    strokeWithGradient(ctx: ctx, path: oInnerPath, lineWidth: innerStrokeW, gradient: oInnerRimGradient, start: oInStart, end: oInEnd)
}

private func makeMavieWordmarkLine(fontSize: CGFloat, kern: CGFloat) -> CTLine {
    let baseFont = NSFont.systemFont(ofSize: fontSize, weight: .bold)
    let font: NSFont
    if let desc = baseFont.fontDescriptor.withDesign(.rounded),
       let rounded = NSFont(descriptor: desc, size: fontSize) {
        font = rounded
    } else {
        font = baseFont
    }
    let word = NSMutableAttributedString(
        string: "Mavie",
        attributes: [
            .font: font,
            .foregroundColor: NSColor(srgbRed: 0.97, green: 0.98, blue: 1.0, alpha: 1.0),
            .kern: kern,
        ]
    )
    let dot = NSAttributedString(
        string: ".",
        attributes: [
            .font: font,
            .foregroundColor: NSColor(srgbRed: 34.0 / 255.0, green: 211.0 / 255.0, blue: 238.0 / 255.0, alpha: 1.0),
        ]
    )
    word.append(dot)
    return CTLineCreateWithAttributedString(word)
}

private func drawLiquidGlassSquircleBadge(ctx: CGContext, rect: CGRect, drawShadow: Bool) {
    let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
    let corner = rect.width * (58.0 / 248.0)
    let squirclePath = CGPath(roundedRect: rect, cornerWidth: corner, cornerHeight: corner, transform: nil)

    if drawShadow {
        ctx.saveGState()
        ctx.setShadow(
            offset: CGSize(width: 0, height: -rect.height * 0.05),
            blur: rect.height * 0.14,
            color: srgbColor(0, 0, 0, 0.58)
        )
        ctx.addPath(squirclePath)
        ctx.setFillColor(srgbColor(11, 14, 26))
        ctx.fillPath()
        ctx.restoreGState()
    }

    ctx.saveGState()
    ctx.addPath(squirclePath)
    ctx.clip()

    let bg = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(20, 26, 50), srgbColor(11, 14, 26), srgbColor(5, 7, 14)] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!
    let vAura = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237, 0.34), srgbColor(59, 130, 246, 0.12), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.55, 1.0]
    )!
    let cAura = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(6, 182, 212, 0.24), srgbColor(59, 130, 246, 0.09), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.52, 1.0]
    )!
    let sheen = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(255, 255, 255, 0.13), srgbColor(255, 255, 255, 0.025), srgbColor(255, 255, 255, 0.0)] as CFArray,
        locations: [0.0, 0.38, 1.0]
    )!
    let borderGrad = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(255, 255, 255, 0.30),
            srgbColor(124, 58, 237, 0.26),
            srgbColor(59, 130, 246, 0.22),
            srgbColor(6, 182, 212, 0.34),
        ] as CFArray,
        locations: [0.0, 0.35, 0.72, 1.0]
    )!
    let topSpec = CGGradient(
        colorsSpace: cs,
        colors: [
            srgbColor(255, 255, 255, 0.0),
            srgbColor(255, 255, 255, 0.32),
            srgbColor(255, 255, 255, 0.46),
            srgbColor(255, 255, 255, 0.32),
            srgbColor(255, 255, 255, 0.0),
        ] as CFArray,
        locations: [0.0, 0.22, 0.50, 0.78, 1.0]
    )!

    ctx.drawLinearGradient(bg, start: CGPoint(x: rect.minX + rect.width * 0.12, y: rect.maxY), end: CGPoint(x: rect.minX + rect.width * 0.88, y: rect.minY), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    ctx.drawRadialGradient(vAura, startCenter: CGPoint(x: rect.minX + rect.width * 0.24, y: rect.maxY - rect.height * 0.24), startRadius: 0, endCenter: CGPoint(x: rect.minX + rect.width * 0.24, y: rect.maxY - rect.height * 0.24), endRadius: rect.width * 0.62, options: [])
    ctx.drawRadialGradient(cAura, startCenter: CGPoint(x: rect.minX + rect.width * 0.62, y: rect.maxY - rect.height * 0.68), startRadius: 0, endCenter: CGPoint(x: rect.minX + rect.width * 0.62, y: rect.maxY - rect.height * 0.68), endRadius: rect.width * 0.58, options: [])
    ctx.drawLinearGradient(sheen, start: CGPoint(x: rect.minX + rect.width * 0.25, y: rect.maxY), end: CGPoint(x: rect.minX + rect.width * 0.55, y: rect.maxY - rect.height * 0.58), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])

    let borderW = max(1.0, rect.width * (2.6 / 248.0))
    let borderInset = borderW * 0.5 + max(0.5, rect.width * (1.2 / 248.0))
    let innerRect = rect.insetBy(dx: borderInset, dy: borderInset)
    let innerCorner = max(2.0, corner - borderInset)
    let innerPath = CGPath(roundedRect: innerRect, cornerWidth: innerCorner, cornerHeight: innerCorner, transform: nil)
    strokeWithGradient(ctx: ctx, path: innerPath, lineWidth: borderW, gradient: borderGrad, start: CGPoint(x: innerRect.minX, y: innerRect.maxY), end: CGPoint(x: innerRect.maxX, y: innerRect.minY))

    let specPath = CGMutablePath()
    let specY = innerRect.maxY - borderW * 0.15
    specPath.move(to: CGPoint(x: innerRect.minX + innerCorner * 0.85, y: specY))
    specPath.addLine(to: CGPoint(x: innerRect.maxX - innerCorner * 0.85, y: specY))
    strokeWithGradient(ctx: ctx, path: specPath, lineWidth: max(0.8, rect.width * (1.8 / 248.0)), gradient: topSpec, start: CGPoint(x: innerRect.minX + innerCorner * 0.85, y: specY), end: CGPoint(x: innerRect.maxX - innerCorner * 0.85, y: specY))

    let emblemSide = rect.width * 0.82
    let emblemRect = CGRect(
        x: rect.midX - emblemSide * 0.5,
        y: rect.midY - emblemSide * 0.5,
        width: emblemSide,
        height: emblemSide
    )
    drawMavieEmblem(ctx: ctx, rect: emblemRect, withBloom: true, opticalBoost: rect.width < 110 ? 1.08 : 1.0)
    ctx.restoreGState()
}

private func makeBitmapContext(width: Int, height: Int) throws -> (NSBitmapImageRep, NSGraphicsContext, CGContext) {
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: width,
        pixelsHigh: height,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: width * 4,
        bitsPerPixel: 32
    ) else {
        throw NSError(domain: "MavieIcon", code: 1, userInfo: [NSLocalizedDescriptionKey: "Bitmap olusturulamadi"])
    }
    rep.size = NSSize(width: width, height: height)
    guard let nsCtx = NSGraphicsContext(bitmapImageRep: rep) else {
        throw NSError(domain: "MavieIcon", code: 2, userInfo: [NSLocalizedDescriptionKey: "GraphicsContext olusturulamadi"])
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = nsCtx
    let ctx = nsCtx.cgContext
    ctx.setAllowsAntialiasing(true)
    ctx.setShouldAntialias(true)
    ctx.setAllowsFontSmoothing(true)
    ctx.setShouldSmoothFonts(true)
    ctx.interpolationQuality = .high
    return (rep, nsCtx, ctx)
}

private func renderTVSplashPNG(width: Int, height: Int) throws -> Data {
    let w = CGFloat(width)
    let h = CGFloat(height)
    let (rep, _, ctx) = try makeBitmapContext(width: width, height: height)
    let fullRect = CGRect(x: 0, y: 0, width: w, height: h)
    let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()

    // Deep opaque obsidian cinema backdrop
    ctx.setFillColor(srgbColor(5, 7, 14))
    ctx.fill(fullRect)
    let bg = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(16, 21, 42), srgbColor(8, 11, 21), srgbColor(4, 6, 12)] as CFArray,
        locations: [0.0, 0.52, 1.0]
    )!
    ctx.drawLinearGradient(bg, start: CGPoint(x: w * 0.15, y: h), end: CGPoint(x: w * 0.85, y: 0), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])

    // Atmospheric cinema violet & cyan glows
    let violetGlow = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237, 0.24), srgbColor(59, 130, 246, 0.08), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!
    ctx.drawRadialGradient(
        violetGlow,
        startCenter: CGPoint(x: w * 0.36, y: h * 0.64),
        startRadius: 0,
        endCenter: CGPoint(x: w * 0.36, y: h * 0.64),
        endRadius: w * 0.42,
        options: []
    )
    let cyanGlow = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(6, 182, 212, 0.18), srgbColor(59, 130, 246, 0.06), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!
    ctx.drawRadialGradient(
        cyanGlow,
        startCenter: CGPoint(x: w * 0.64, y: h * 0.36),
        startRadius: 0,
        endCenter: CGPoint(x: w * 0.64, y: h * 0.36),
        endRadius: w * 0.40,
        options: []
    )

    // Centered Liquid Glass squircle badge above the wordmark
    let badgeSize: CGFloat = h * 0.285 // ~308px on 1080p
    let badgeRect = CGRect(
        x: (w - badgeSize) * 0.5,
        y: h * 0.475,
        width: badgeSize,
        height: badgeSize
    )
    drawLiquidGlassSquircleBadge(ctx: ctx, rect: badgeRect, drawShadow: true)

    // Crisp "Mavie." wordmark below badge
    let line = makeMavieWordmarkLine(fontSize: h * 0.088, kern: -2.6)
    let bounds = CTLineGetBoundsWithOptions(line, .useGlyphPathBounds)
    let tx = (w - bounds.width) * 0.5 - bounds.origin.x
    let ty = badgeRect.minY - h * 0.065 - bounds.height - bounds.origin.y
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -4), blur: 22, color: srgbColor(59, 130, 246, 0.25))
    ctx.textMatrix = .identity
    ctx.textPosition = CGPoint(x: tx, y: ty)
    CTLineDraw(line, ctx)
    ctx.restoreGState()

    // Subtle luminous violet -> blue -> cyan horizon accent line under wordmark
    let barW = w * 0.11
    let barH: CGFloat = 3.5
    let barRect = CGRect(x: (w - barW) * 0.5, y: ty - h * 0.042, width: barW, height: barH)
    let barPath = CGPath(roundedRect: barRect, cornerWidth: barH * 0.5, cornerHeight: barH * 0.5, transform: nil)
    let accentGrad = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237, 0.0), srgbColor(124, 58, 237, 0.85), srgbColor(59, 130, 246, 0.95), srgbColor(6, 182, 212, 0.85), srgbColor(6, 182, 212, 0.0)] as CFArray,
        locations: [0.0, 0.22, 0.50, 0.78, 1.0]
    )!
    ctx.saveGState()
    ctx.addPath(barPath)
    ctx.clip()
    ctx.drawLinearGradient(accentGrad, start: CGPoint(x: barRect.minX, y: barRect.midY), end: CGPoint(x: barRect.maxX, y: barRect.midY), options: [])
    ctx.restoreGState()

    NSGraphicsContext.restoreGraphicsState()
    guard let pngData = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "MavieIcon", code: 3, userInfo: [NSLocalizedDescriptionKey: "TV splash PNG kodlanamadi"])
    }
    return pngData
}

private func renderAndroidTVBannerPNG(width: Int, height: Int) throws -> Data {
    let w = CGFloat(width)
    let h = CGFloat(height)
    let (rep, _, ctx) = try makeBitmapContext(width: width, height: height)
    let fullRect = CGRect(x: 0, y: 0, width: w, height: h)
    let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()

    // Full-bleed opaque Liquid Glass obsidian canvas (Android TV applies its own rounded card mask)
    ctx.setFillColor(srgbColor(6, 8, 16))
    ctx.fill(fullRect)
    let bg = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(20, 26, 52), srgbColor(10, 14, 27), srgbColor(5, 7, 14)] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!
    ctx.drawLinearGradient(bg, start: CGPoint(x: w * 0.08, y: h), end: CGPoint(x: w * 0.92, y: 0), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])

    // Dual violet (left behind emblem) & cyan (right behind wordmark) ambient auras
    let violetGlow = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237, 0.34), srgbColor(59, 130, 246, 0.12), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.52, 1.0]
    )!
    ctx.drawRadialGradient(
        violetGlow,
        startCenter: CGPoint(x: w * 0.24, y: h * 0.58),
        startRadius: 0,
        endCenter: CGPoint(x: w * 0.24, y: h * 0.58),
        endRadius: w * 0.45,
        options: []
    )
    let cyanGlow = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(6, 182, 212, 0.24), srgbColor(59, 130, 246, 0.09), srgbColor(5, 7, 14, 0.0)] as CFArray,
        locations: [0.0, 0.50, 1.0]
    )!
    ctx.drawRadialGradient(
        cyanGlow,
        startCenter: CGPoint(x: w * 0.78, y: h * 0.32),
        startRadius: 0,
        endCenter: CGPoint(x: w * 0.78, y: h * 0.32),
        endRadius: w * 0.44,
        options: []
    )

    // Subtle Liquid Glass top sheen
    let sheen = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(255, 255, 255, 0.10), srgbColor(255, 255, 255, 0.02), srgbColor(255, 255, 255, 0.0)] as CFArray,
        locations: [0.0, 0.42, 1.0]
    )!
    ctx.drawLinearGradient(sheen, start: CGPoint(x: w * 0.30, y: h), end: CGPoint(x: w * 0.52, y: h * 0.36), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])

    // Measure horizontal lockup: [96x96 Liquid Glass M+o badge] + 18px gap + ["Mavie."]
    let badgeSize: CGFloat = h * 0.54 // 97.2px on 320x180
    let gap: CGFloat = w * 0.056      // ~18px
    let line = makeMavieWordmarkLine(fontSize: h * 0.295, kern: -1.6)
    let textBounds = CTLineGetBoundsWithOptions(line, .useGlyphPathBounds)
    let lockupW = badgeSize + gap + textBounds.width
    let startX = (w - lockupW) * 0.5

    let badgeRect = CGRect(
        x: startX,
        y: (h - badgeSize) * 0.5,
        width: badgeSize,
        height: badgeSize
    )
    drawLiquidGlassSquircleBadge(ctx: ctx, rect: badgeRect, drawShadow: true)

    let textX = badgeRect.maxX + gap - textBounds.origin.x
    // Optical vertical center of cap height against badge center
    let textY = h * 0.5 - textBounds.height * 0.5 - textBounds.origin.y + 3.0
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -2), blur: 10, color: srgbColor(6, 182, 212, 0.28))
    ctx.textMatrix = .identity
    ctx.textPosition = CGPoint(x: textX, y: textY)
    CTLineDraw(line, ctx)
    ctx.restoreGState()

    // Crisp violet -> blue -> cyan accent underline beneath the wordmark
    let barRect = CGRect(
        x: badgeRect.maxX + gap + 2.0,
        y: badgeRect.minY + 14.0,
        width: textBounds.width * 0.62,
        height: 3.0
    )
    let barPath = CGPath(roundedRect: barRect, cornerWidth: 1.5, cornerHeight: 1.5, transform: nil)
    let accentGrad = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237), srgbColor(59, 130, 246), srgbColor(6, 182, 212)] as CFArray,
        locations: [0.0, 0.52, 1.0]
    )!
    ctx.saveGState()
    ctx.addPath(barPath)
    ctx.clip()
    ctx.drawLinearGradient(accentGrad, start: CGPoint(x: barRect.minX, y: barRect.midY), end: CGPoint(x: barRect.maxX, y: barRect.midY), options: [])
    ctx.restoreGState()

    // Subtle bottom hairline edge glow
    let edgeGrad = CGGradient(
        colorsSpace: cs,
        colors: [srgbColor(124, 58, 237, 0.0), srgbColor(124, 58, 237, 0.38), srgbColor(6, 182, 212, 0.42), srgbColor(6, 182, 212, 0.0)] as CFArray,
        locations: [0.0, 0.28, 0.72, 1.0]
    )!
    ctx.saveGState()
    ctx.clip(to: CGRect(x: 0, y: 0, width: w, height: 2.5))
    ctx.drawLinearGradient(edgeGrad, start: CGPoint(x: 0, y: 1.25), end: CGPoint(x: w, y: 1.25), options: [])
    ctx.restoreGState()

    NSGraphicsContext.restoreGraphicsState()
    guard let pngData = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "MavieIcon", code: 3, userInfo: [NSLocalizedDescriptionKey: "Android TV banner PNG kodlanamadi"])
    }
    return pngData
}

let args = CommandLine.arguments
if args.count >= 4 && args[1] == "--render-squircles" {
    // Helper mode: --render-squircles <output_dir> <size1> [size2 ...]
    let outDir = URL(fileURLWithPath: args[2], isDirectory: true)
    try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
    for rawSize in args.dropFirst(3) {
        guard let sz = Int(rawSize), sz > 0 else {
            fputs("Invalid pixel size: \(rawSize)\n", stderr)
            exit(2)
        }
        let data = try renderMavieIconPNG(pixelSize: sz, style: .webSquircle)
        try data.write(to: outDir.appendingPathComponent("squircle_\(sz).png"), options: [.atomic])
    }
    exit(0)
}
if args.count >= 4 && args[1] == "--render-tv-assets" {
    // Helper mode: --render-tv-assets <tv_assets_dir> <android_tv_banner_png>
    let tvDir = URL(fileURLWithPath: args[2], isDirectory: true)
    let bannerURL = URL(fileURLWithPath: args[3], isDirectory: false)
    let fm = FileManager.default
    try fm.createDirectory(at: tvDir, withIntermediateDirectories: true)
    try fm.createDirectory(at: bannerURL.deletingLastPathComponent(), withIntermediateDirectories: true)

    for sz in [512, 130, 80] {
        let iconData = try renderMavieIconPNG(pixelSize: sz, style: .iOSFullBleed)
        try iconData.write(to: tvDir.appendingPathComponent("icon-\(sz).png"), options: [.atomic])
    }
    let splashData = try renderTVSplashPNG(width: 1920, height: 1080)
    try splashData.write(to: tvDir.appendingPathComponent("splash-1920x1080.png"), options: [.atomic])

    let bannerData = try renderAndroidTVBannerPNG(width: 320, height: 180)
    try bannerData.write(to: bannerURL, options: [.atomic])
    print("Generated TV assets (icon-512, icon-130, icon-80, splash-1920x1080) and 320x180 Android TV banner.")
    exit(0)
}

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
        data = try renderMavieIconPNG(pixelSize: spec.pixels, style: .macOSGrid)
        renderedBySize[spec.pixels] = data
    }
    try data.write(to: iconsetDir.appendingPathComponent(spec.filename), options: [.atomic])
    try data.write(to: macAssetsDir.appendingPathComponent(spec.filename), options: [.atomic])
}

let iosData = try renderMavieIconPNG(pixelSize: 1024, style: .iOSFullBleed)
try iosData.write(to: iosIconURL, options: [.atomic])
print("Generated \(specs.count) macOS icons and 1024x1024 iOS AppIcon.")
