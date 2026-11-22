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

private struct MavieOpenCArcShape: Shape {
    var radius: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.addArc(
            center: CGPoint(x: rect.midX, y: rect.midY),
            radius: radius,
            startAngle: .degrees(38.66),
            endAngle: .degrees(321.34),
            clockwise: false
        )
        return path
    }
}

private struct MaviePlayTriangleShape: Shape {
    var scale: CGFloat

    func path(in rect: CGRect) -> Path {
        let cx = rect.midX
        let cy = rect.midY
        var path = Path()
        path.move(to: CGPoint(x: cx - 8.0 * scale, y: cy - 17.0 * scale))
        path.addLine(to: CGPoint(x: cx + 23.0 * scale, y: cy))
        path.addLine(to: CGPoint(x: cx - 8.0 * scale, y: cy + 17.0 * scale))
        path.closeSubpath()
        return path
    }
}

public struct MavieLogoMark: View {
    public var size: CGFloat
    public var animateSweep: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulseActive = false

    public init(size: CGFloat = 44, animateSweep: Bool = false) {
        self.size = size
        self.animateSweep = animateSweep
    }

    public var body: some View {
        let corner = size * (44.0 / 192.0)
        let markScale = (size * 0.72) / 120.0
        let arcRadius = 38.42 * markScale
        let arcStroke = max(2.0, 16.0 * markScale)
        let dotDiameter = max(2.5, 10.4 * markScale)

        ZStack {
            RoundedRectangle(cornerRadius: corner, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 20.0 / 255.0, green: 24.0 / 255.0, blue: 43.0 / 255.0),
                            Color(red: 8.0 / 255.0, green: 11.0 / 255.0, blue: 20.0 / 255.0)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: corner, style: .continuous)
                        .strokeBorder(MavieTheme.cyanDot.opacity(0.16), lineWidth: 1)
                )

            MavieOpenCArcShape(radius: arcRadius)
                .stroke(
                    MavieTheme.brandGradient,
                    style: StrokeStyle(lineWidth: arcStroke, lineCap: .round, lineJoin: .round)
                )
                .opacity(animateSweep && !reduceMotion && pulseActive ? 0.92 : 1.0)

            MaviePlayTriangleShape(scale: markScale)
                .fill(Color.white)
                .overlay(
                    MaviePlayTriangleShape(scale: markScale)
                        .stroke(Color.white, style: StrokeStyle(lineWidth: max(1.0, 4.0 * markScale), lineJoin: .round))
                )

            Circle()
                .fill(MavieTheme.cyanDot)
                .frame(width: dotDiameter, height: dotDiameter)
                .scaleEffect(animateSweep && !reduceMotion && pulseActive ? 1.24 : 1.0)
                .shadow(color: MavieTheme.cyanDot.opacity(0.65), radius: max(2.0, 4.0 * markScale))
                .offset(x: 32.0 * markScale)
        }
        .frame(width: size, height: size)
        .shadow(
            color: MavieTheme.purple.opacity(animateSweep && !reduceMotion && pulseActive ? 0.44 : 0.28),
            radius: size * 0.22,
            y: size * 0.08
        )
        .accessibilityHidden(true)
        .onAppear {
            guard animateSweep && !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: true)) {
                pulseActive = true
            }
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
