import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(PurchaseStore.self) private var purchases
    @Environment(\.scenePhase) private var phase

    var body: some View {
        Group {
            if model.isSignedIn || model.isDemo {
                TabView {
                    NavigationStack { JobsView() }.tabItem { Label("Workspace", systemImage: "square.grid.2x2") }
                    NavigationStack { DraftsView() }.tabItem { Label("Drafts", systemImage: "doc.text") }
                    NavigationStack { PlansView() }.tabItem { Label("Credits", systemImage: "sparkles") }
                    NavigationStack { ProfileView() }.tabItem { Label("Profile", systemImage: "person.crop.circle") }
                }
                .safeAreaInset(edge: .top, spacing: 0) {
                    if model.isDemo {
                        HStack {
                            Label("Demo · sample jobs", systemImage: "play.circle")
                            Spacer()
                            Button("Sign in") { Task { await model.signOut() } }
                        }.font(.caption.weight(.medium)).padding(.horizontal).padding(.vertical, 8)
                            .background(Theme.card)
                    }
                }
            } else { WelcomeView() }
        }
        .task(id: model.account?.id) { await purchases.recover(model) }
        .onChange(of: phase) { _, value in
            if value == .active, model.isSignedIn {
                Task { await model.reload(); await purchases.recover(model) }
            }
        }
    }
}

struct WelcomeView: View {
    @Environment(AppModel.self) private var model
    @State private var email = ""
    @State private var code = ""
    @State private var sentTo: String?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    HStack(spacing: 10) {
                        Image(systemName: "checkmark.seal.fill").foregroundStyle(Theme.accent)
                        Text("JustHireMe").font(.title3.weight(.bold))
                    }.padding(.top, 24)
                    Spacer(minLength: 20)
                    Eyebrow(text: "Your next chapter")
                    Text("A little focus.\nA better next role.")
                        .font(.system(.largeTitle, design: .serif, weight: .medium))
                    Text("Keep your best opportunities together. Turn your real experience into thoughtful applications.")
                        .font(.title3).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 16) {
                        Label("A clear application pipeline", systemImage: "rectangle.3.group")
                        Label("Drafts grounded in your experience", systemImage: "doc.badge.gearshape")
                        Label("Flexible plans. Credits that carry forward.", systemImage: "sparkles")
                    }.font(.subheadline).padding(22).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 24))
                    VStack(spacing: 14) {
                        TextField("Email address", text: $email)
                            .textContentType(.emailAddress).keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                            .padding().background(Theme.card, in: RoundedRectangle(cornerRadius: 14))
                            .disabled(sentTo != nil)
                        if let sentTo {
                            Text("Enter the code sent to \(sentTo)").font(.caption).foregroundStyle(.secondary)
                            TextField("Email code", text: $code).textContentType(.oneTimeCode).keyboardType(.numberPad)
                                .padding().background(Theme.card, in: RoundedRectangle(cornerRadius: 14))
                        }
                        ActionButton(title: sentTo == nil ? "Continue with email" : "Sign in", busy: busy) {
                            Task { await submit() }
                        }.disabled(email.isEmpty || (sentTo != nil && code.count < 6))
                        if sentTo != nil {
                            Button("Use another email or resend") { sentTo = nil; code = "" }.font(.callout)
                        }
                        Button("Explore the demo") { model.demo() }.padding(.top, 6)
                            .accessibilityIdentifier("demo.explore")
                    }
                    if let error { InlineMessage(text: error) }
                    Text("Your profile syncs securely with your account. You choose whether to share it with AI for drafting.")
                        .font(.footnote).foregroundStyle(.secondary)
                    LegalLinks()
                }.padding(24).frame(maxWidth: 600)
                    .frame(maxWidth: .infinity)
            }.background(Theme.background)
        }
    }

    private func submit() async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            if let sentTo {
                try await model.api.verify(email: sentTo, code: code.trimmingCharacters(in: .whitespacesAndNewlines))
                model.isSignedIn = true
                await model.reload()
            } else {
                let normalized = email.trimmingCharacters(in: .whitespacesAndNewlines)
                try await model.api.requestCode(email: normalized)
                sentTo = normalized
            }
        } catch { self.error = error.localizedDescription }
    }
}

struct LegalLinks: View {
    var body: some View {
        HStack(spacing: 18) {
            if let url = try? Configuration.url("PrivacyURL") { Link("Privacy", destination: url) }
            if let url = try? Configuration.url("TermsURL") { Link("Terms", destination: url) }
            if let url = try? Configuration.url("SupportURL") { Link("Support", destination: url) }
        }.font(.footnote)
    }
}

#Preview { RootView().environment(AppModel()).environment(PurchaseStore()) }
