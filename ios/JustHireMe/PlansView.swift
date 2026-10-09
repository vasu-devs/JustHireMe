import StoreKit
import SwiftUI

struct PlansView: View {
    @Environment(AppModel.self) private var model
    @Environment(PurchaseStore.self) private var store
    @State private var manageSubscriptions = false
    @State private var selection: PreviewPlan = .monthly
    @State private var previewConfirmation = false
    @State private var previewMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                JournalHeading(eyebrow: "Invest in your next chapter", title: "Your pace.\nYour plan.")
                HStack {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("\(model.balance)")
                            .font(Theme.mono(32))
                            .accessibilityIdentifier("plan.balance")
                        Text(model.isDemo ? "Demo credits" : "Available credits").font(Theme.sans(15)).foregroundStyle(Theme.copy)
                        if model.isDemo { Text("Sample plan: \(model.demoPlan?.title ?? "Pay as you go")").font(Theme.sans(12)) }
                    }
                    Spacer()
                    Image(systemName: "sparkles").font(.largeTitle).foregroundStyle(Theme.accent)
                }.padding(24).journalCard(tint: Theme.yellow)
                Text("One application package uses \(model.account?.tailorCost ?? 5) credits. Save and track jobs for free. Purchased credits never expire.")
                    .foregroundStyle(Theme.copy)
                if model.isDemo {
                    ForEach(PreviewPlan.allCases) { plan in
                        Button { selection = plan; previewMessage = nil } label: {
                            HStack(alignment: .top, spacing: 14) {
                                Image(systemName: selection == plan ? "largecircle.fill.circle" : "circle").font(.title2).foregroundStyle(Theme.accent)
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(plan.title).font(Theme.heading(21))
                                    Text(plan.detail).font(Theme.sans(15))
                                    Text("\(plan.credits / 5) application packages").font(Theme.sans(13)).foregroundStyle(Theme.copy)
                                    Text(plan.note).font(Theme.sans(11)).foregroundStyle(Theme.copy)
                                }
                                Spacer(minLength: 0)
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
                                .journalCard(tint: selection == plan ? Theme.green : .clear)
                                .overlay(RoundedRectangle(cornerRadius: 16).stroke(selection == plan ? Theme.accent : .clear, lineWidth: 1.5))
                        }.buttonStyle(.plain).accessibilityIdentifier("plan.\(plan.id)")
                            .accessibilityAddTraits(selection == plan ? .isSelected : [])
                    }
                    Text("Preview only. Live prices appear in the App Store checkout after sign-in.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                    ActionButton(title: "Try \(selection.title.lowercased()) in preview") { previewConfirmation = true }
                        .accessibilityIdentifier("plan.preview")
                    if let previewMessage { InlineMessage(text: previewMessage).accessibilityIdentifier("plan.success") }
                } else if model.account?.billingAvailable != true {
                    previewPlan("Focus weekly", subtitle: "30 credits each week · auto-renews", tint: Theme.blue)
                    previewPlan("Pro monthly", subtitle: "150 credits each month · auto-renews", tint: Theme.green)
                    previewPlan("A little extra", subtitle: "50 credits · one-time purchase", tint: Theme.pink)
                    InlineMessage(text: model.isDemo ? "Sign in to see live App Store prices and purchase a plan." : "Purchases are not configured on this server yet.")
                } else {
                    ForEach(store.products, id: \.id) { product in
                        productCard(product)
                    }
                    if store.products.isEmpty {
                        Button("Load App Store plans") { Task { await store.load(model) } }
                    }
                    HStack {
                        Button("Restore purchases") { Task { await store.restore(model) } }
                        Spacer()
                        Button("Manage plan") { manageSubscriptions = true }
                    }.font(Theme.sans(13)).disabled(store.busy)
                }
                if let message = store.message { InlineMessage(text: message) }
                Text("Weekly and monthly plans renew automatically until cancelled. Each successful renewal adds credits that carry forward. You can manage or cancel a subscription in your Apple account. Deleting JustHireMe does not cancel it.")
                    .font(Theme.sans(13)).foregroundStyle(Theme.copy)
                LegalLinks()
                if !model.ledger.isEmpty {
                    Text("Credit activity").font(Theme.heading(20))
                    ForEach(model.ledger) { item in
                        HStack {
                            Text(item.reason).font(Theme.sans(15))
                            Spacer()
                            Text(item.amount > 0 ? "+\(item.amount)" : "\(item.amount)").monospacedDigit()
                        }.padding(.vertical, 8)
                    }
                }
            }.padding(24).frame(maxWidth: 640).frame(maxWidth: .infinity)
        }.journalScreen().navigationTitle("Credits").navigationBarTitleDisplayMode(.inline)
            .task(id: model.account?.billingAvailable) { await store.load(model) }
            .manageSubscriptionsSheet(isPresented: $manageSubscriptions)
            .confirmationDialog("Preview \(selection.title)?", isPresented: $previewConfirmation, titleVisibility: .visible) {
                Button("Add \(selection.credits) demo credits") {
                    do { try model.previewPurchase(selection); previewMessage = "You’re ready. \(selection.credits) demo credits added. No payment was made." }
                    catch { previewMessage = error.localizedDescription }
                }
            } message: { Text("This simulates choosing a plan. No payment, subscription, or renewal is created.") }
    }

    private func previewPlan(_ title: String, subtitle: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(Theme.heading(21))
            Text(subtitle).font(Theme.sans(15)).foregroundStyle(Theme.copy)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(22)
            .journalCard(tint: tint)
    }

    private func productCard(_ product: Product) -> some View {
        let offering = store.catalog.first { $0.id == product.id }
        let active = model.account?.activeSubscriptions.contains(product.id) == true
        return VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(product.displayName).font(Theme.heading(20))
                Spacer()
                if active { Text("Active").font(.caption.weight(.bold)).foregroundStyle(Theme.accent) }
            }
            Text(product.description).foregroundStyle(Theme.copy)
            if let offering {
                Text("\(offering.credits) credits" + (offering.period.map { " each \($0)" } ?? " · no expiry"))
                    .font(.subheadline.weight(.medium))
            }
            Text(product.displayPrice + (offering?.period.map { " / \($0)" } ?? " once"))
                .font(.title2.weight(.bold))
            ActionButton(title: active ? "Current plan" : "Continue", busy: store.busy) {
                Task { await store.buy(product, model: model) }
            }.disabled(active)
        }.padding(22).journalCard(tint: Theme.green)
    }
}
