import SwiftUI

public enum MavieTheme {
    public static let purple = Color(red: 124.0 / 255.0, green: 58.0 / 255.0, blue: 237.0 / 255.0)
    public static let blue = Color(red: 59.0 / 255.0, green: 130.0 / 255.0, blue: 246.0 / 255.0)
    public static let turquoise = Color(red: 6.0 / 255.0, green: 182.0 / 255.0, blue: 212.0 / 255.0)
    public static let coral = purple
    public static let amber = turquoise
    public static let bg = Color(red: 10.0 / 255.0, green: 13.0 / 255.0, blue: 22.0 / 255.0)
    public static let bgDeep = Color(red: 7.0 / 255.0, green: 10.0 / 255.0, blue: 18.0 / 255.0)
    public static let panel = Color(red: 18.0 / 255.0, green: 23.0 / 255.0, blue: 38.0 / 255.0)
    public static let panelElevated = Color(red: 26.0 / 255.0, green: 33.0 / 255.0, blue: 52.0 / 255.0)
    public static let border = Color.white.opacity(0.11)
    public static let muted = Color(red: 168.0 / 255.0, green: 181.0 / 255.0, blue: 214.0 / 255.0)
    public static let success = Color(red: 52.0 / 255.0, green: 211.0 / 255.0, blue: 153.0 / 255.0)
    public static let warning = Color(red: 56.0 / 255.0, green: 189.0 / 255.0, blue: 248.0 / 255.0)
    public static let danger = Color(red: 244.0 / 255.0, green: 63.0 / 255.0, blue: 94.0 / 255.0)

    public static let brandGradient = LinearGradient(
        colors: [purple, blue, turquoise],
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

public struct MavieLogoMark: View {
    public var size: CGFloat
    public var animateSweep: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotationDegrees: Double = 0

    public init(size: CGFloat = 44, animateSweep: Bool = false) {
        self.size = size
        self.animateSweep = animateSweep
    }

    public var body: some View {
        let corner = size * 0.24
        let ringWidth = max(2.5, size * 0.08)

        ZStack {
            RoundedRectangle(cornerRadius: corner, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 23.0 / 255.0, green: 27.0 / 255.0, blue: 36.0 / 255.0),
                            Color(red: 11.0 / 255.0, green: 13.0 / 255.0, blue: 18.0 / 255.0)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: corner, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
                )

            Circle()
                .stroke(
                    AngularGradient(
                        gradient: Gradient(colors: [
                            MavieTheme.coral,
                            MavieTheme.amber,
                            MavieTheme.coral.opacity(0.35),
                            MavieTheme.coral
                        ]),
                        center: .center
                    ),
                    style: StrokeStyle(lineWidth: ringWidth, lineCap: .round)
                )
                .padding(size * 0.19)
                .rotationEffect(.degrees(rotationDegrees))

            Image(systemName: "play.fill")
                .font(.system(size: size * 0.30, weight: .bold))
                .foregroundStyle(.white)
                .offset(x: size * 0.03)
        }
        .frame(width: size, height: size)
        .shadow(color: MavieTheme.coral.opacity(0.28), radius: size * 0.22, y: size * 0.08)
        .accessibilityHidden(true)
        .onAppear {
            guard animateSweep && !reduceMotion else { return }
            withAnimation(.linear(duration: 4.5).repeatForever(autoreverses: false)) {
                rotationDegrees = 360
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
                            colors: [.white, MavieTheme.amber.opacity(0.95)],
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
            )
            .shadow(color: MavieTheme.coral.opacity(configuration.isPressed ? 0.15 : 0.35), radius: 10, y: 4)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1.0)
            .opacity(configuration.isPressed ? 0.92 : 1.0)
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.72), value: configuration.isPressed)
    }
}

public struct MavieGhostButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
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
                    .fill(MavieTheme.panelElevated.opacity(configuration.isPressed ? 0.95 : 0.75))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(MavieTheme.border, lineWidth: 1)
                    )
            )
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1.0)
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.75), value: configuration.isPressed)
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
                    .fill(MavieTheme.panel)
                    .overlay(
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .strokeBorder(MavieTheme.border, lineWidth: 1)
                    )
            )
    }
}

public extension View {
    func mavieCard(cornerRadius: CGFloat = 16) -> some View {
        modifier(MavieCardModifier(cornerRadius: cornerRadius))
    }
}
