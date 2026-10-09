import SwiftUI

enum NotebookInk {
    static let lavender = Theme.adaptive(0xe4dcf5, 0x3c354f)
    static let mint = Theme.adaptive(0xd9ecde, 0x304a42)
    static let peach = Theme.adaptive(0xf9ded0, 0x513a34)
    static let sky = Theme.adaptive(0xdbeaf6, 0x303f53)
    static let butter = Theme.adaptive(0xf8edbd, 0x4c4530)
    static let pink = Theme.adaptive(0xf5deeb, 0x4e3548)
    static func color(_ index: Int) -> Color { [lavender, mint, peach, sky, butter, pink][abs(index) % 6] }
}

struct PencilOutline: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: 9, y: 2))
        p.addQuadCurve(to: CGPoint(x: r.maxX-8, y: 3), control: CGPoint(x: r.midX, y: -1))
        p.addQuadCurve(to: CGPoint(x: r.maxX-2, y: r.maxY-9), control: CGPoint(x: r.maxX+1, y: r.midY))
        p.addQuadCurve(to: CGPoint(x: 7, y: r.maxY-2), control: CGPoint(x: r.midX, y: r.maxY+2))
        p.addQuadCurve(to: CGPoint(x: 9, y: 2), control: CGPoint(x: -2, y: r.midY))
        p.closeSubpath()
        return p
    }
}

struct CrayonStroke: View {
    var color: Color
    var body: some View {
        Canvas { context, size in
            for row in 0..<7 {
                var path = Path()
                let y = CGFloat(row) * 2 + 2
                path.move(to: CGPoint(x: CGFloat(row % 3) * 2, y: y))
                for x in stride(from: 0, through: Int(size.width), by: 7) {
                    path.addLine(to: CGPoint(x: CGFloat(x), y: y + sin(Double(x + row * 9) * 0.08) * 1.5))
                }
                context.stroke(path, with: .color(color.opacity(0.65)), style: StrokeStyle(lineWidth: 2.3, lineCap: .round))
            }
        }.frame(height: 18).accessibilityHidden(true)
    }
}

struct RuledPaper: View {
    var body: some View {
        Canvas { context, size in
            for y in stride(from: 28, to: size.height, by: 28) {
                var p = Path(); p.move(to: CGPoint(x: 0, y: y)); p.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(p, with: .color(Theme.ink.opacity(0.035)), lineWidth: 0.7)
            }
            var margin = Path(); margin.move(to: CGPoint(x: 14, y: 0)); margin.addLine(to: CGPoint(x: 14, y: size.height))
            context.stroke(margin, with: .color(Theme.coral.opacity(0.15)), lineWidth: 1)
        }.allowsHitTesting(false).accessibilityHidden(true)
    }
}

struct NotebookCard<Content: View>: View {
    var tint: Color = Theme.card
    var ruled = false
    @ViewBuilder var content: Content
    var body: some View {
        content.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(tint)
            .overlay { if ruled { RuledPaper() } }
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(PencilOutline().stroke(Theme.ink.opacity(0.19), lineWidth: 0.85))
            .shadow(color: Theme.ink.opacity(0.035), radius: 0, x: 3, y: 4)
    }
}

struct NotebookHeading: View {
    let chapter: String
    let title: String
    let subtitle: String
    var tint: Color = NotebookInk.lavender
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Text(chapter).font(Theme.sans(12)).foregroundStyle(Theme.copy)
                CrayonStroke(color: tint).frame(width: 42, height: 10).clipped()
            }.padding(.bottom, 2)
            Text(title).font(Theme.display(32)).fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(subtitle).font(Theme.sans(14)).foregroundStyle(Theme.copy).lineSpacing(2)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct NotebookButton: View {
    let title: String
    var symbol = "arrow.right"
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) { Text(title); Spacer(); Image(systemName: symbol) }
                .font(Theme.sans(15, bold: true)).foregroundStyle(Theme.buttonInk)
                .padding(.horizontal, 20).padding(.vertical, 17).background(Theme.accent, in: RoundedRectangle(cornerRadius: 12))
                .overlay(PencilOutline().stroke(Theme.ink.opacity(0.22), lineWidth: 1))
        }.buttonStyle(.plain)
    }
}

struct NotebookPage<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) { content }
                .padding(.horizontal, 22).padding(.vertical, 20).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }.background(Theme.background).journalScreen().scrollDismissesKeyboard(.interactively)
            .navigationBarTitleDisplayMode(.inline)
    }
}

struct NotebookTag: View {
    let text: String
    var tint: Color = NotebookInk.lavender
    var body: some View {
        Text(text).font(Theme.sans(11, bold: true)).padding(.horizontal, 10).padding(.vertical, 7)
            .background(tint, in: RoundedRectangle(cornerRadius: 5)).foregroundStyle(Theme.ink)
    }
}

enum NotebookTab: Hashable { case profile, matches, applications, grow, plan }
struct NotebookRootView: View {
    @Environment(NotebookModel.self) private var book
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var phase
    @State private var tab = NotebookTab.profile
    var body: some View {
        TabView(selection: $tab) {
            NavigationStack { NotebookProfileView() }.tabItem { Label("Profile", systemImage: "book.closed") }.tag(NotebookTab.profile)
            NavigationStack { RecommendedRolesView() }.tabItem { Label("For You", systemImage: "briefcase") }.tag(NotebookTab.matches)
            NavigationStack { ApplicationTrackerView() }.tabItem { Label("Applications", systemImage: "chart.bar.xaxis") }.tag(NotebookTab.applications)
            NavigationStack { GrowthView() }.tabItem { Label("Grow", systemImage: "leaf") }.tag(NotebookTab.grow)
            NavigationStack {
                if book.isPreview { ApplicationPlansView() } else { ConnectedPlansView() }
            }.tabItem { Label("Plan", systemImage: "ticket") }.tag(NotebookTab.plan)
        }
        .task(id: "\(book.accountID ?? "")-\(phase == .active)") {
            guard book.isConnected, phase == .active else { return }
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(10))
                    try Task.checkCancellation()
                    try await book.refreshConnection()
                } catch is CancellationError { return }
                catch let error as AppError where error.isUnauthorized {
                    await model.signOut()
                    model.message = error.localizedDescription
                    return
                }
                catch { book.connectionMessage = error.localizedDescription }
            }
        }
    }
}
