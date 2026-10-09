import Foundation
import Observation
import StoreKit

@MainActor @Observable
final class PurchaseStore {
    private(set) var products: [Product] = []
    private(set) var catalog: [CatalogProduct] = []
    private(set) var busy = false
    var message: String?

    func load(_ model: AppModel) async {
        guard !model.isDemo, model.account?.billingAvailable == true else { return }
        do {
            catalog = try await model.api.get("v1/products", as: [CatalogProduct].self)
            let loaded = try await Product.products(for: catalog.map(\.id))
            products = catalog.compactMap { item in loaded.first { $0.id == item.id } }
            if products.isEmpty { message = "Plans are not available from the App Store yet. Please retry later." }
        } catch { message = error.localizedDescription }
    }

    func listen(_ model: AppModel) async {
        for await result in Transaction.updates {
            if Task.isCancelled { return }
            guard !model.isDemo, model.isSignedIn, model.account != nil else { continue }
            do { try await deliver(result, model: model) }
            catch { message = error.localizedDescription }
        }
    }

    func recover(_ model: AppModel) async {
        guard !model.isDemo, model.account?.billingAvailable == true else { return }
        for await result in Transaction.unfinished {
            do { try await deliver(result, model: model) }
            catch { message = error.localizedDescription }
        }
    }

    func buy(_ product: Product, model: AppModel) async {
        guard !busy, !model.isDemo, let token = model.account?.purchaseToken else { return }
        busy = true
        defer { busy = false }
        do {
            switch try await product.purchase(options: [.appAccountToken(token)]) {
            case .success(let result): try await deliver(result, model: model)
            case .pending: message = "Your purchase is awaiting approval. Credits will appear when it completes."
            case .userCancelled: break
            @unknown default: message = "Please check your purchase status and try restoring purchases."
            }
        } catch { message = error.localizedDescription }
    }

    func restore(_ model: AppModel) async {
        guard !busy, !model.isDemo else { return }
        busy = true
        defer { busy = false }
        do {
            try await AppStore.sync()
            for await result in Transaction.currentEntitlements { try await deliver(result, model: model) }
            // Consumable balances live on the server; unfinished purchases are delivered here.
            await recover(model)
            await model.reload()
            message = "Purchase sync completed. Your account balance has been refreshed."
        } catch { message = error.localizedDescription }
    }

    private func deliver(_ result: VerificationResult<Transaction>, model: AppModel) async throws {
        guard case .verified(let transaction) = result else {
            throw AppError.message("This purchase could not be verified. No credits were added.")
        }
        guard transaction.appAccountToken == model.account?.purchaseToken else {
            throw AppError.message("Sign in to the JustHireMe account used for this purchase to recover it.")
        }
        let bytes = try JSONSerialization.data(withJSONObject: ["signed_transaction": result.jwsRepresentation])
        _ = try await model.api.raw("v1/billing/transactions", method: "POST", body: bytes)
        // The backend committed delivery before StoreKit is told this transaction is finished.
        await transaction.finish()
        await model.reload()
    }
}
