import SwiftUI

@main
struct JustHireMeApp: App {
    @State private var model = AppModel()
    @State private var purchases = PurchaseStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(purchases)
                .tint(Theme.accent)
                .task { await model.bootstrap() }
                .task { await purchases.listen(model) }
        }
    }
}
