import SwiftUI

@main
struct JustHireMeApp: App {
    @State private var model = AppModel()
    @State private var purchases = PurchaseStore()

    init() { Theme.configureChrome() }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(purchases)
                .tint(Theme.accent)
                .font(Theme.sans())
                .foregroundStyle(Theme.ink)
                .modifier(SimulatorAppearance())
                .task { await model.bootstrap() }
                .task { await purchases.listen(model) }
        }
    }
}

private struct SimulatorAppearance: ViewModifier {
    @Environment(\.dynamicTypeSize) private var textSize
    func body(content: Content) -> some View {
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        content
            .preferredColorScheme(args.contains("--appearance-dark") ? .dark : nil)
            .dynamicTypeSize(args.contains("--large-text") ? .accessibility2 : textSize)
        #else
        content
        #endif
    }
}
