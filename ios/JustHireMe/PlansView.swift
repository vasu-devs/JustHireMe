import StoreKit
import SwiftUI

struct PlansView: View {
    @Environment(AppModel.self) private var model
    @Environment(PurchaseStore.self) private var store
    @State private var manageSubscriptions = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Eyebrow(text: "Invest in your next chapter")
                Text("Your pace.\nYour plan.").font(.system(.largeTitle, design: .serif, weight: .medium))
                HStack {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(model.isDemo ? "—" : "\(model.account?.balance ?? 0)")
                            .font(.system(.largeTitle, design: .rounded, weight: .bold))
                        Text("Available credits").font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "sparkles").font(.largeTitle).foregroundStyle(Theme.accent)
                }.padding(24).background(Theme.card, in: RoundedRectangle(cornerRadius: 24))
                Text("One application package uses \(model.account?.tailorCost ?? 5) credits. Save and track jobs for free. Purchased credits never expire.")
                    .foregroundStyle(.secondary)
                if model.isDemo || model.account?.billingAvailable != true {
                    previewPlan("Focus weekly", subtitle: "30 credits each week · auto-renews")
                    previewPlan("Pro monthly", subtitle: "150 credits each month · auto-renews")
                    previewPlan("A little extra", subtitle: "50 credits · one-time purchase")
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
                    }.font(.footnote).disabled(store.busy)
                }
                if let message = store.message { InlineMessage(text: message) }
                Text("Weekly and monthly plans renew automatically until cancelled. Each successful renewal adds credits that carry forward. You can manage or cancel a subscription in your Apple account. Deleting JustHireMe does not cancel it.")
                    .font(.footnote).foregroundStyle(.secondary)
                LegalLinks()
                if !model.ledger.isEmpty {
                    Text("Credit activity").font(.title3.weight(.semibold))
                    ForEach(model.ledger) { item in
                        HStack {
                            Text(item.reason).font(.subheadline)
                            Spacer()
                            Text(item.amount > 0 ? "+\(item.amount)" : "\(item.amount)").monospacedDigit()
                        }.padding(.vertical, 8)
                    }
                }
            }.padding(24).frame(maxWidth: 640).frame(maxWidth: .infinity)
        }.background(Theme.background).navigationTitle("Credits").navigationBarTitleDisplayMode(.inline)
            .task(id: model.account?.billingAvailable) { await store.load(model) }
            .manageSubscriptionsSheet(isPresented: $manageSubscriptions)
    }

    private func previewPlan(_ title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(22)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 22))
    }

    private func productCard(_ product: Product) -> some View {
        let offering = store.catalog.first { $0.id == product.id }
        let active = model.account?.activeSubscriptions.contains(product.id) == true
        return VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(product.displayName).font(.title3.weight(.semibold))
                Spacer()
                if active { Text("Active").font(.caption.weight(.bold)).foregroundStyle(Theme.accent) }
            }
            Text(product.description).foregroundStyle(.secondary)
            if let offering {
                Text("\(offering.credits) credits" + (offering.period.map { " each \($0)" } ?? " · no expiry"))
                    .font(.subheadline.weight(.medium))
            }
            Text(product.displayPrice + (offering?.period.map { " / \($0)" } ?? " once"))
                .font(.title2.weight(.bold))
            ActionButton(title: active ? "Current plan" : "Continue", busy: store.busy) {
                Task { await store.buy(product, model: model) }
            }.disabled(active)
        }.padding(22).background(Theme.card, in: RoundedRectangle(cornerRadius: 22))
    }
}
