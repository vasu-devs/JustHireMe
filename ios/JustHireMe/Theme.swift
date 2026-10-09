import SwiftUI
import UIKit

// Source of truth: src/production-journal.css and src/demo/atelier.css in the desktop app.
enum Theme {
    static func adaptive(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            uiColor(traits.userInterfaceStyle == .dark ? dark : light)
        })
    }
    static func uiColor(_ hex: UInt32) -> UIColor {
        UIColor(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
                blue: CGFloat(hex & 255) / 255, alpha: 1)
    }
    static let accent = adaptive(0x596ba0, 0xc3baf2)
    static let ink = adaptive(0x353946, 0xf4f1fb)
    static let copy = adaptive(0x636777, 0xc6c6d7)
    static let faint = adaptive(0x747888, 0xaaa9bd)
    static let background = adaptive(0xf6f5f0, 0x20222b)
    static let chrome = adaptive(0xfbfaf6, 0x272a35)
    static let card = adaptive(0xfffef9, 0x2e313d)
    static let page = adaptive(0xfffaf0, 0x302620)
    static let pageAlt = adaptive(0xfbf2df, 0x29211d)
    static let red = adaptive(0xac4e43, 0xe29581)
    static let coral = adaptive(0xdc745f, 0xee816d)
    static let blue = adaptive(0xaad3df, 0x91bdcb)
    static let pink = adaptive(0xe8b8c4, 0xd89aaa)
    static let green = adaptive(0xafd0b5, 0x94bea1)
    static let yellow = adaptive(0xedce70, 0xd6b85f)
    static let line = ink.opacity(0.15)
    static let buttonInk = adaptive(0xffffff, 0x2b211c)

    static func display(_ size: CGFloat = 34) -> Font { .custom("InstrumentSerif-Regular", size: size, relativeTo: .title) }
    static func sans(_ size: CGFloat = 16, bold: Bool = false) -> Font {
        .custom(bold ? "InstrumentSans-Bold" : "InstrumentSans-Regular", size: size, relativeTo: .body)
    }
    static func heading(_ size: CGFloat = 19) -> Font { .custom("InstrumentSans-Bold", size: size, relativeTo: .headline) }
    static func mono(_ size: CGFloat = 10) -> Font { .custom("GeistMono-Regular", size: size, relativeTo: .caption) }

    @MainActor static func configureChrome() {
        let nav = UINavigationBarAppearance()
        nav.configureWithOpaqueBackground()
        nav.backgroundColor = UIColor(chrome)
        nav.titleTextAttributes = [.font: UIFont(name: "InstrumentSans-Bold", size: 17) ?? UIFont.boldSystemFont(ofSize: 17),
                                   .foregroundColor: UIColor(ink)]
        nav.largeTitleTextAttributes = [.font: UIFont(name: "InstrumentSerif-Regular", size: 34) ?? UIFont.systemFont(ofSize: 34),
                                        .foregroundColor: UIColor(ink)]
        UINavigationBar.appearance().standardAppearance = nav
        UINavigationBar.appearance().scrollEdgeAppearance = nav
        let tabs = UITabBarAppearance()
        tabs.configureWithOpaqueBackground()
        tabs.backgroundColor = UIColor(chrome)
        UITabBar.appearance().standardAppearance = tabs
        UITabBar.appearance().scrollEdgeAppearance = tabs
        UITabBar.appearance().unselectedItemTintColor = UIColor(copy)
    }
}

struct JournalSurface: ViewModifier {
    var tint: Color = .clear
    func body(content: Content) -> some View {
        content.background {
            UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 16, bottomTrailingRadius: 11, topTrailingRadius: 20)
                .fill(Theme.card).overlay(tint.opacity(0.18))
                .clipShape(UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 16, bottomTrailingRadius: 11, topTrailingRadius: 20))
        }.overlay {
            UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 16, bottomTrailingRadius: 11, topTrailingRadius: 20)
                .stroke(Theme.line, lineWidth: 1)
        }
    }
}

extension View {
    func journalCard(tint: Color = .clear) -> some View { modifier(JournalSurface(tint: tint)) }
    func journalScreen() -> some View {
        font(Theme.sans()).foregroundStyle(Theme.ink)
            .background(Theme.background)
            .toolbarBackground(Theme.chrome, for: .navigationBar, .tabBar)
            .toolbarBackground(.visible, for: .navigationBar, .tabBar)
    }
}

struct JournalRule: View {
    var body: some View {
        Rectangle().fill(Theme.line).frame(height: 1).accessibilityHidden(true)
    }
}

struct BrandMark: View {
    var body: some View {
        // Exact paths from the desktop's justhireme-mark.svg, scaled from its 48-point viewBox.
        Canvas { context, size in
            context.scaleBy(x: size.width / 48, y: size.height / 48)
            var j = Path()
            j.move(to: CGPoint(x: 15, y: 7)); j.addLine(to: CGPoint(x: 27, y: 7)); j.addLine(to: CGPoint(x: 27, y: 27))
            j.addCurve(to: CGPoint(x: 14, y: 41), control1: CGPoint(x: 27, y: 36), control2: CGPoint(x: 22, y: 41))
            j.addCurve(to: CGPoint(x: 4, y: 31), control1: CGPoint(x: 8, y: 41), control2: CGPoint(x: 4, y: 37))
            context.stroke(j, with: .color(Color(uiColor: Theme.uiColor(0xe87965))), style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))
            var check = Path()
            check.move(to: CGPoint(x: 23, y: 25)); check.addLine(to: CGPoint(x: 31, y: 33)); check.addLine(to: CGPoint(x: 44, y: 15))
            context.stroke(check, with: .color(Theme.ink), style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round))
            context.fill(Path(ellipseIn: CGRect(x: 37, y: 3, width: 8, height: 8)), with: .color(Theme.green))
        }.frame(width: 32, height: 32).accessibilityHidden(true)
    }
}

struct JournalHeading: View {
    let eyebrow: String
    let title: String
    var note: String = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow(text: eyebrow)
            Text(title).font(Theme.display()).fixedSize(horizontal: false, vertical: true)
            if !note.isEmpty { Text(note).font(Theme.sans(14)).foregroundStyle(Theme.copy) }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct Eyebrow: View {
    let text: String
    var body: some View {
        Text(text.uppercased()).font(Theme.mono()).tracking(1).foregroundStyle(Theme.faint)
    }
}

struct ActionButton: View {
    let title: String
    var busy = false
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack {
                if busy { ProgressView().tint(Theme.buttonInk) }
                Text(title).font(Theme.sans(15, bold: true))
            }.foregroundStyle(Theme.buttonInk).frame(maxWidth: .infinity).padding(.vertical, 12)
        }
        .buttonStyle(.borderedProminent).buttonBorderShape(.capsule)
        .disabled(busy)
    }
}

struct InlineMessage: View {
    let text: String
    var body: some View {
        Label(text, systemImage: "info.circle")
            .font(Theme.sans(14)).foregroundStyle(Theme.copy).padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .journalCard(tint: Theme.blue)
    }
}
