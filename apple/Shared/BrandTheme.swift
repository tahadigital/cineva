import SwiftUI

public enum MavieTheme {
    public static let purple = Color(red: 124.0 / 255.0, green: 58.0 / 255.0, blue: 237.0 / 255.0)
    public static let blue = Color(red: 59.0 / 255.0, green: 130.0 / 255.0, blue: 246.0 / 255.0)
    public static let turquoise = Color(red: 6.0 / 255.0, green: 182.0 / 255.0, blue: 212.0 / 255.0)
    public static let cyanDot = Color(red: 34.0 / 255.0, green: 211.0 / 255.0, blue: 238.0 / 255.0)
    public static let coral = purple
    public static let amber = turquoise
    public static let bg = Color(red: 10.0 / 255.0, green: 13.0 / 255.0, blue: 22.0 / 255.0)
    public static let bgDeep = Color(red: 7.0 / 255.0, green: 10.0 / 255.0, blue: 18.0 / 255.0)
    public static let panel = Color(red: 18.0 / 255.0, green: 23.0 / 255.0, blue: 38.0 / 255.0)
    public static let panelElevated = Color(red: 26.0 / 255.0, green: 33.0 / 255.0, blue: 52.0 / 255.0)
    public static let glassTint = Color(red: 20.0 / 255.0, green: 26.0 / 255.0, blue: 48.0 / 255.0).opacity(0.42)
    public static let glassTintElevated = Color(red: 30.0 / 255.0, green: 38.0 / 255.0, blue: 66.0 / 255.0).opacity(0.50)
    public static let border = Color.white.opacity(0.14)
    public static let muted = Color(red: 168.0 / 255.0, green: 181.0 / 255.0, blue: 214.0 / 255.0)
    public static let success = Color(red: 52.0 / 255.0, green: 211.0 / 255.0, blue: 153.0 / 255.0)
    public static let warning = Color(red: 56.0 / 255.0, green: 189.0 / 255.0, blue: 248.0 / 255.0)
    public static let danger = Color(red: 244.0 / 255.0, green: 63.0 / 255.0, blue: 94.0 / 255.0)

    public static let brandGradient = LinearGradient(
        colors: [purple, blue, turquoise],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    public static let specularBorder = LinearGradient(
        colors: [
            Color.white.opacity(0.28),
            Color.white.opacity(0.10),
            turquoise.opacity(0.16)
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    public static let specularAccentBorder = LinearGradient(
        colors: [
            Color.white.opacity(0.36),
            cyanDot.opacity(0.24),
            purple.opacity(0.28)
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    public static let cinemaBackdrop = RadialGradient(
        colors: [
            purple.opacity(0.24),
            turquoise.opacity(0.12),
            bgDeep
        ],
        center: .top,
        startRadius: 20,
        endRadius: 520
    )
}

private struct MavieMMonogramShape: Shape {
    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 256.0
        let ox = rect.midX - 128.0 * s
        let oy = rect.midY - 128.0 * s
        func pt(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: ox + x * s, y: oy + y * s)
        }

        var path = Path()
        path.move(to: pt(23.50, 40.00))
        path.addCurve(to: pt(34.50, 28.50), control1: pt(23.50, 32.50), control2: pt(27.20, 29.20))
        path.addCurve(to: pt(95.50, 29.00), control1: pt(56.50, 26.20), control2: pt(77.50, 26.50))
        path.addCurve(to: pt(105.40, 38.00), control1: pt(101.00, 29.80), control2: pt(103.80, 32.80))
        path.addLine(to: pt(129.00, 128.50))
        path.addLine(to: pt(152.60, 38.00))
        path.addCurve(to: pt(162.50, 29.00), control1: pt(154.20, 32.80), control2: pt(157.00, 29.80))
        path.addCurve(to: pt(223.50, 28.50), control1: pt(180.50, 26.50), control2: pt(201.50, 26.20))
        path.addCurve(to: pt(234.50, 40.00), control1: pt(230.80, 29.20), control2: pt(234.50, 32.50))
        path.addLine(to: pt(234.50, 207.50))
        path.addCurve(to: pt(216.00, 224.50), control1: pt(234.50, 218.50), control2: pt(227.50, 224.50))
        path.addLine(to: pt(195.50, 224.50))
        path.addCurve(to: pt(184.50, 213.00), control1: pt(188.50, 224.50), control2: pt(184.50, 220.20))
        path.addLine(to: pt(184.50, 110.00))
        path.addLine(to: pt(180.00, 110.00))
        path.addLine(to: pt(150.50, 214.00))
        path.addCurve(to: pt(136.00, 224.50), control1: pt(148.50, 221.00), control2: pt(143.50, 224.50))
        path.addLine(to: pt(123.50, 224.50))
        path.addCurve(to: pt(107.50, 208.50), control1: pt(113.00, 224.50), control2: pt(107.50, 219.00))
        path.addLine(to: pt(107.50, 181.50))
        path.addCurve(to: pt(80.18, 131.61), control1: pt(107.50, 160.61), control2: pt(96.99, 141.42))
        path.addCurve(to: pt(27.20, 134.66), control1: pt(63.36, 121.81), control2: pt(42.99, 122.98))
        path.addCurve(to: pt(23.50, 130.00), control1: pt(24.80, 136.44), control2: pt(23.50, 134.60))
        path.closeSubpath()
        return path
    }
}

private struct MavieLensEllipseShape: Shape {
    var rx: CGFloat
    var ry: CGFloat

    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 256.0
        let ox = rect.midX - 128.0 * s
        let oy = rect.midY - 128.0 * s
        let ellipseRect = CGRect(
            x: ox + (56.0 - rx) * s,
            y: oy + (181.5 - ry) * s,
            width: rx * 2.0 * s,
            height: ry * 2.0 * s
        )
        return Path(ellipseIn: ellipseRect)
    }
}

private struct MavieLensDonutShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = MavieLensEllipseShape(rx: 35.0, ry: 39.0).path(in: rect)
        path.addPath(MavieLensEllipseShape(rx: 13.8, ry: 15.6).path(in: rect))
        return path
    }
}

public struct MavieLogoMark: View {
    public var size: CGFloat
    public var animateSweep: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulseActive = false

    private var shouldPulse: Bool {
        animateSweep && !reduceMotion
    }

    public init(size: CGFloat = 44, animateSweep: Bool = false) {
        self.size = size
        self.animateSweep = animateSweep
    }

    public var body: some View {
        let corner = size * (58.0 / 248.0)
        let emblemSize = size * 0.81
        let unit = emblemSize / 256.0
        let opticalBoost: CGFloat = size <= 24 ? 1.25 : (size <= 36 ? 1.12 : 1.0)
        let outerStroke = max(1.3, 10.4 * unit * opticalBoost)
        let innerStroke = max(1.1, 8.8 * unit * opticalBoost)
        let isAnimatingNow = shouldPulse && pulseActive

        let obsidianCore = LinearGradient(
            colors: [
                Color(red: 22.0 / 255.0, green: 28.0 / 255.0, blue: 50.0 / 255.0),
                Color(red: 9.0 / 255.0, green: 13.0 / 255.0, blue: 24.0 / 255.0),
                Color(red: 3.0 / 255.0, green: 5.0 / 255.0, blue: 10.0 / 255.0)
            ],
            startPoint: UnitPoint(x: 0.18, y: 0.0),
            endPoint: UnitPoint(x: 0.82, y: 1.0)
        )
        let mRimGradient = LinearGradient(
            stops: [
                .init(color: MavieTheme.purple, location: 0.0),
                .init(color: MavieTheme.blue, location: 0.22),
                .init(color: MavieTheme.turquoise, location: 0.50),
                .init(color: MavieTheme.blue, location: 0.78),
                .init(color: MavieTheme.purple, location: 1.0)
            ],
            startPoint: UnitPoint(x: 0.04, y: 0.44),
            endPoint: UnitPoint(x: 0.96, y: 0.56)
        )
        let oRimGradient = LinearGradient(
            colors: [MavieTheme.purple, MavieTheme.turquoise, MavieTheme.blue],
            startPoint: UnitPoint(x: 0.08, y: 0.50),
            endPoint: UnitPoint(x: 0.92, y: 0.50)
        )
        let oInnerRimGradient = LinearGradient(
            colors: [MavieTheme.turquoise, MavieTheme.blue, MavieTheme.purple],
            startPoint: .top,
            endPoint: .bottom
        )

        ZStack {
            RoundedRectangle(cornerRadius: corner, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 18.0 / 255.0, green: 23.0 / 255.0, blue: 44.0 / 255.0),
                            Color(red: 11.0 / 255.0, green: 14.0 / 255.0, blue: 26.0 / 255.0),
                            Color(red: 5.0 / 255.0, green: 7.0 / 255.0, blue: 14.0 / 255.0)
                        ],
                        startPoint: UnitPoint(x: 0.12, y: 0.0),
                        endPoint: UnitPoint(x: 0.88, y: 1.0)
                    )
                )
                .overlay(
                    RadialGradient(
                        colors: [MavieTheme.purple.opacity(0.30), MavieTheme.blue.opacity(0.10), .clear],
                        center: UnitPoint(x: 0.24, y: 0.24),
                        startRadius: 0,
                        endRadius: size * 0.62
                    )
                )
                .overlay(
                    RadialGradient(
                        colors: [MavieTheme.turquoise.opacity(0.22), MavieTheme.blue.opacity(0.08), .clear],
                        center: UnitPoint(x: 0.62, y: 0.68),
                        startRadius: 0,
                        endRadius: size * 0.58
                    )
                )
                .overlay(
                    LinearGradient(
                        colors: [Color.white.opacity(0.12), Color.white.opacity(0.025), .clear],
                        startPoint: UnitPoint(x: 0.25, y: 0.0),
                        endPoint: UnitPoint(x: 0.55, y: 0.58)
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: corner, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: corner, style: .continuous)
                        .strokeBorder(
                            LinearGradient(
                                colors: [
                                    Color.white.opacity(0.28),
                                    MavieTheme.purple.opacity(0.24),
                                    MavieTheme.blue.opacity(0.20),
                                    MavieTheme.turquoise.opacity(0.32)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: max(0.8, size * (2.5 / 256.0))
                        )
                )

            ZStack {
                if size >= 36 {
                    ZStack {
                        MavieMMonogramShape()
                            .stroke(
                                mRimGradient,
                                style: StrokeStyle(lineWidth: outerStroke * 1.25, lineCap: .round, lineJoin: .round)
                            )
                        MavieLensEllipseShape(rx: 35.0, ry: 39.0)
                            .stroke(oRimGradient, lineWidth: outerStroke * 1.25)
                    }
                    .blur(radius: max(1.6, 5.2 * unit))
                    .opacity(isAnimatingNow ? 0.52 : 0.30)
                }

                MavieMMonogramShape()
                    .fill(obsidianCore)
                MavieMMonogramShape()
                    .stroke(
                        mRimGradient,
                        style: StrokeStyle(lineWidth: outerStroke, lineCap: .round, lineJoin: .round)
                    )

                MavieLensDonutShape()
                    .fill(obsidianCore, style: FillStyle(eoFill: true))
                MavieLensEllipseShape(rx: 35.0, ry: 39.0)
                    .stroke(oRimGradient, lineWidth: outerStroke)
                MavieLensEllipseShape(rx: 13.8, ry: 15.6)
                    .stroke(oInnerRimGradient, lineWidth: innerStroke)
                    .scaleEffect(isAnimatingNow ? 1.05 : 1.0)
            }
            .frame(width: emblemSize, height: emblemSize)
            .offset(y: 1.5 * unit)
        }
        .frame(width: size, height: size)
        .shadow(
            color: MavieTheme.purple.opacity(isAnimatingNow ? 0.44 : 0.28),
            radius: size * 0.22,
            y: size * 0.08
        )
        .accessibilityHidden(true)
        .animation(
            shouldPulse
                ? .easeInOut(duration: 1.5).repeatForever(autoreverses: true)
                : .linear(duration: 0.1),
            value: pulseActive
        )
        .onAppear {
            pulseActive = shouldPulse
        }
        .onDisappear {
            pulseActive = false
        }
        .onChange(of: shouldPulse) { newValue in
            pulseActive = newValue
        }
    }
}

public struct MavieWordmark: View {
    public var subtitle: String?
    public var markSize: CGFloat

    public init(subtitle: String? = nil, markSize: CGFloat = 34) {
        self.subtitle = subtitle
        self.markSize = markSize
    }

    public var body: some View {
        HStack(spacing: 10) {
            MavieLogoMark(size: markSize)
            VStack(alignment: .leading, spacing: 2) {
                Text("Mavie")
                    .font(.system(size: markSize * 0.62, weight: .bold, design: .rounded))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.white, MavieTheme.cyanDot.opacity(0.95)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(MavieTheme.muted)
                }
            }
        }
    }
}

public struct MaviePrimaryButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isHovered = false
    public var compact: Bool

    public init(compact: Bool = false) {
        self.compact = compact
    }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(compact ? .subheadline.weight(.semibold) : .body.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, compact ? 14 : 18)
            .padding(.vertical, compact ? 10 : 12)
            .frame(minWidth: 44, minHeight: 44)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(MavieTheme.brandGradient)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(
                                LinearGradient(
                                    colors: [Color.white.opacity(0.38), Color.white.opacity(0.08)],
                                    startPoint: .top,
                                    endPoint: .bottom
                                ),
                                lineWidth: 1
                            )
                    )
            )
            .shadow(color: MavieTheme.purple.opacity(configuration.isPressed ? 0.18 : (isHovered ? 0.45 : 0.34)), radius: isHovered ? 14 : 10, y: 4)
            .scaleEffect(reduceMotion ? 1.0 : (configuration.isPressed ? 0.97 : (isHovered ? 1.02 : 1.0)))
            .opacity(configuration.isPressed ? 0.92 : 1.0)
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.72), value: configuration.isPressed)
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.74), value: isHovered)
            .onHover { isHovered = $0 }
    }
}

public struct MavieGhostButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isHovered = false
    public var compact: Bool

    public init(compact: Bool = false) {
        self.compact = compact
    }

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(compact ? .subheadline.weight(.medium) : .body.weight(.medium))
            .foregroundStyle(.white)
            .padding(.horizontal, compact ? 12 : 16)
            .padding(.vertical, compact ? 9 : 11)
            .frame(minWidth: 44, minHeight: 44)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(MavieTheme.glassTintElevated.opacity(configuration.isPressed ? 1.0 : (isHovered ? 0.95 : 0.78)))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(MavieTheme.specularBorder, lineWidth: 1)
                    )
            )
            .scaleEffect(reduceMotion ? 1.0 : (configuration.isPressed ? 0.97 : (isHovered ? 1.02 : 1.0)))
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.75), value: configuration.isPressed)
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.75), value: isHovered)
            .onHover { isHovered = $0 }
    }
}

public struct MavieInteractiveCardButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isHovered = false

    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(reduceMotion ? 1.0 : (configuration.isPressed ? 0.98 : (isHovered ? 1.015 : 1.0)))
            .animation(reduceMotion ? nil : .spring(response: 0.28, dampingFraction: 0.76), value: configuration.isPressed)
            .animation(reduceMotion ? nil : .spring(response: 0.28, dampingFraction: 0.76), value: isHovered)
            .onHover { isHovered = $0 }
    }
}

public struct MavieCardModifier: ViewModifier {
    public var cornerRadius: CGFloat
    public init(cornerRadius: CGFloat = 16) {
        self.cornerRadius = cornerRadius
    }

    public func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .fill(MavieTheme.glassTint)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .strokeBorder(MavieTheme.specularBorder, lineWidth: 1)
                    )
            )
            .shadow(color: Color.black.opacity(0.26), radius: 14, y: 8)
    }
}

public struct MavieGlassPillModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    public var selected: Bool
    public var cornerRadius: CGFloat?

    public init(selected: Bool = false, cornerRadius: CGFloat? = nil) {
        self.selected = selected
        self.cornerRadius = cornerRadius
    }

    public func body(content: Content) -> some View {
        content
            .background(pillBackground)
            .animation(reduceMotion ? nil : .spring(response: 0.28, dampingFraction: 0.78), value: selected)
    }

    @ViewBuilder
    private var pillBackground: some View {
        if let radius = cornerRadius {
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(selected ? AnyShapeStyle(MavieTheme.brandGradient) : AnyShapeStyle(.ultraThinMaterial))
                .overlay(
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .fill(selected ? Color.clear : MavieTheme.glassTint)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .strokeBorder(selected ? MavieTheme.specularAccentBorder : MavieTheme.specularBorder, lineWidth: 1)
                )
        } else {
            Capsule()
                .fill(selected ? AnyShapeStyle(MavieTheme.brandGradient) : AnyShapeStyle(.ultraThinMaterial))
                .overlay(
                    Capsule()
                        .fill(selected ? Color.clear : MavieTheme.glassTint)
                )
                .overlay(
                    Capsule()
                        .strokeBorder(selected ? MavieTheme.specularAccentBorder : MavieTheme.specularBorder, lineWidth: 1)
                )
        }
    }
}

public extension View {
    func mavieCard(cornerRadius: CGFloat = 16) -> some View {
        modifier(MavieCardModifier(cornerRadius: cornerRadius))
    }

    func mavieGlassPill(selected: Bool = false, cornerRadius: CGFloat? = nil) -> some View {
        modifier(MavieGlassPillModifier(selected: selected, cornerRadius: cornerRadius))
    }
}
