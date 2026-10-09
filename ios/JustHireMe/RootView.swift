import SwiftUI

enum AppTab: Hashable { case overview, pipeline, drafts, profile }

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(PurchaseStore.self) private var purchases
    @Environment(\.scenePhase) private var phase
    @State private var tab: AppTab = .overview

    var body: some View {
        Group {
            if model.isSignedIn || model.isDemo {
                VStack(spacing: 0) {
                    if model.isDemo {
                        HStack {
                            Image(systemName: "circle.inset.filled").foregroundStyle(Theme.accent)
                            Text("Preview · no real submissions").font(Theme.sans(11))
                            Spacer()
                            Button("Sign in") { Task { await model.signOut() } }
                        }.font(Theme.sans(12)).foregroundStyle(Theme.copy).padding(.horizontal).padding(.vertical, 8)
                            .background(Theme.chrome)
                    }
                    if Configuration.connectedTest {
                        Text("Connected test · employer and payment fixtures")
                            .font(Theme.sans(10)).foregroundStyle(Theme.copy).padding(8)
                            .frame(maxWidth: .infinity).background(NotebookInk.butter)
                    }
                    if let message = model.message { InlineMessage(text: message) }
                    NotebookRootView().environment(model.notebook)
                }
            } else { WelcomeView() }
        }
        .onChange(of: model.isDemo) { _, _ in tab = .overview }
        .onChange(of: model.isSignedIn) { _, _ in tab = .overview }
        .task(id: model.account?.id) { if !Configuration.connectedTest { await purchases.recover(model) } }
        .onChange(of: phase) { _, value in
            if value == .active, model.isSignedIn {
                Task { await model.reload(); if !Configuration.connectedTest { await purchases.recover(model) } }
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
                        BrandMark()
                        Text("JustHireMe").font(Theme.heading(23))
                    }.padding(.top, 24)
                    Eyebrow(text: "Your job search")
                    Text("Find your next role.")
                        .font(Theme.display(36))
                    Text("Build your profile, find relevant jobs and keep track of your applications.")
                        .font(Theme.sans(16)).foregroundStyle(Theme.copy)
                    VStack(alignment: .leading, spacing: 16) {
                        Label("An editable profile", systemImage: "book")
                        Label("Job matches and one-tap apply", systemImage: "paperplane")
                        Label("Application tracking and study suggestions", systemImage: "leaf")
                    }.font(Theme.sans(15)).padding(22).frame(maxWidth: .infinity, alignment: .leading)
                        .journalCard(tint: Theme.yellow)
                    VStack(spacing: 14) {
                        TextField("Email address", text: $email)
                            .textContentType(.emailAddress).keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                            .padding().background(Theme.card, in: RoundedRectangle(cornerRadius: 14))
                            .disabled(sentTo != nil)
                        if let sentTo {
                            Text("Enter the code sent to \(sentTo)").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                            TextField("Email code", text: $code).textContentType(.oneTimeCode).keyboardType(.numberPad)
                                .padding().background(Theme.card, in: RoundedRectangle(cornerRadius: 14))
                        }
                        ActionButton(title: sentTo == nil ? "Continue with email" : "Sign in", busy: busy) {
                            Task { await submit() }
                        }.disabled(email.isEmpty || (sentTo != nil && code.count < 6))
                        if sentTo != nil {
                            Button("Use another email or resend") { sentTo = nil; code = "" }.font(Theme.sans(15))
                        }
                        Button("Explore the demo") { model.demo() }.padding(.top, 6)
                            .accessibilityIdentifier("demo.explore")
                    }
                    if let error { InlineMessage(text: error) }
                    Text("Sign in to sync your profile and applications, or explore with sample data.")
                        .font(Theme.sans(13)).foregroundStyle(Theme.copy)
                    LegalLinks()
                }.padding(24).frame(maxWidth: 600)
                    .frame(maxWidth: .infinity)
            }.journalScreen().toolbar(.hidden, for: .navigationBar)
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
        }.font(Theme.sans(13))
    }
}

#Preview { RootView().environment(AppModel()).environment(PurchaseStore()) }
