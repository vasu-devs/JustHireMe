import SwiftUI
import StoreKit
import PDFKit
import CoreTransferable
import UniformTypeIdentifiers

struct ConnectedProfileControls: View {
    @Environment(NotebookModel.self) private var book
    @Environment(AppModel.self) private var model
    @State private var settings = false
    @State private var reloadConfirmation = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(book.profileDirty ? "Unsaved changes" : "Saved to your account", systemImage: book.profileDirty ? "pencil" : "checkmark.icloud")
                    .font(Theme.sans(12)).accessibilityIdentifier("connected.profile-state")
                Spacer()
                Button("Settings") { settings = true }.font(Theme.sans(12, bold: true)).accessibilityIdentifier("connected.settings")
            }
            if book.profileDirty {
                NotebookButton(title: book.isBusy ? "Saving…" : "Save profile", symbol: "checkmark") {
                    Task { do { try await book.saveConnectedProfile() } catch { book.connectionMessage = error.localizedDescription } }
                }.disabled(book.isBusy).accessibilityIdentifier("connected.save")
            }
            if let message = book.connectionMessage { InlineMessage(text: message) }
        }.sheet(isPresented: $settings) {
            NavigationStack {
                Form {
                    @Bindable var book = book
                    Section("Application details") {
                        TextField("Application email", text: $book.candidate.email).textInputAutocapitalization(.never).keyboardType(.emailAddress)
                        TextField("Phone (optional)", text: $book.candidate.phone).keyboardType(.phonePad)
                        TextField("LinkedIn URL (optional)", text: $book.candidate.linkedin).keyboardType(.URL).textInputAutocapitalization(.never)
                    }
                    Section("Job recommendations") {
                        Toggle("Enable recommendations", isOn: $book.preferences.enabled)
                        Toggle("Share professional profile with TypeSafe for matching", isOn: $book.preferences.matchingConsent)
                        Toggle("Share role and location terms with the job-search provider", isOn: $book.preferences.discoveryConsent)
                        Text("Matching consent covers your professional evidence and job descriptions. Search consent shares role and location terms, not your contact details.").font(.footnote)
                    }
                    Section("Applications") {
                        Toggle("Authorize submissions when I tap Apply or start auto-apply", isOn: $book.candidate.submissionConsent)
                        Toggle("Allow Anthropic to select résumé content", isOn: $book.candidate.tailoringConsent)
                            .disabled(book.capabilities?.resumeTailoringAvailable != true)
                        Toggle("Email me after confirmed submission", isOn: $book.candidate.emailNotifications)
                            .disabled(book.capabilities?.emailNotificationsAvailable != true)
                        Text("Required legal or eligibility answers are never guessed. Without AI tailoring, the résumé uses your supplied facts.").font(.footnote)
                    }
                    Section {
                        Button("Reload saved profile") { reloadConfirmation = true }
                        Button("Sign out", role: .destructive) { Task { await model.signOut() } }
                    }
                    ConnectedAccountData()
                }.navigationTitle("Account settings")
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { settings = false } } }
                    .confirmationDialog("Discard unsaved edits and reload?", isPresented: $reloadConfirmation) {
                        Button("Reload saved profile", role: .destructive) {
                            Task { do { try await book.refreshConnection(loadProfile: true) } catch { book.connectionMessage = error.localizedDescription } }
                        }
                    }
            }
        }
    }
}

struct ConnectedAccountData: View {
    @Environment(AppModel.self) private var model
    @State private var busy = false
    @State private var confirmDelete = false
    @State private var document: ExportDocument?
    @State private var exporting = false
    @State private var message: String?
    var body: some View {
        Section("Your data") {
            Button("Export account data") {
                perform { document = ExportDocument(data: try await model.api.raw("v1/export")); exporting = true }
            }
            Button("Delete account", role: .destructive) { confirmDelete = true }
            Text("Deleting removes your saved profile, application history and remaining allowance. It cannot recall applications already sent. Apple subscriptions must be cancelled separately.").font(.footnote)
            Link("Manage Apple subscriptions", destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
            if let message { Text(message).font(.footnote) }
        }.disabled(busy)
            .fileExporter(isPresented: $exporting, document: document, contentType: .json, defaultFilename: "justhireme-account") { result in
                document = nil
                if case .failure(let error) = result { message = error.localizedDescription }
            }
            .confirmationDialog("Permanently delete your account?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete my account and data", role: .destructive) {
                    perform {
                        let account = model.account?.id
                        _ = try await model.api.raw("v1/account", method: "DELETE")
                        if let account { try? DraftEditStorage.remove(accountID: account) }
                        await model.signOut()
                    }
                }
            }
    }
    private func perform(_ action: @escaping () async throws -> Void) {
        busy = true
        Task { defer { busy = false }; do { try await action() } catch { message = error.localizedDescription } }
    }
}

struct ConnectedAutomationView: View {
    @Environment(NotebookModel.self) private var book
    @Environment(\.dismiss) private var dismiss
    @State private var maximum = 10
    @State private var daily = 2
    @State private var threshold = 80
    @State private var confirm = false
    @State private var busy = false
    @State private var message: String?
    var body: some View {
        NavigationStack {
            NotebookPage {
                NotebookHeading(chapter: "Jobs / Preferences", title: "Auto-apply", subtitle: "Choose how many attempts to queue and when to stop.", tint: NotebookInk.butter)
                NotebookCard(ruled: true) {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(book.profile.targetRoles).font(Theme.heading(18))
                        Text(book.profile.location).font(Theme.sans(14))
                        Text("Uses your saved profile and matching preferences. Edit them in Profile before starting.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                    }
                }
                ForEach(book.campaigns) { campaign in
                    NotebookCard(tint: NotebookInk.mint) {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(campaign.status.capitalized).font(Theme.heading()).accessibilityIdentifier("campaign.status")
                            Text("\(campaign.reserved) of \(campaign.maximum) attempts queued · up to \(campaign.dailyLimit)/day")
                            if campaign.status == "active" {
                                Button("Pause auto-apply") { perform { try await book.pauseCampaign(campaign.id) } }.accessibilityIdentifier("campaign.pause")
                            }
                        }
                    }
                }
                if !book.campaigns.contains(where: { $0.status == "active" }) {
                    NotebookCard(tint: NotebookInk.butter) {
                        VStack(spacing: 18) {
                            Stepper("Up to \(maximum) attempts", value: $maximum, in: 1...1000)
                            Stepper("Up to \(daily) per day", value: $daily, in: 1...100).accessibilityIdentifier("campaign.daily")
                            Stepper("Relevance above \(threshold)%", value: $threshold, in: 80...99)
                        }.font(Theme.sans(14))
                    }
                    NotebookButton(title: "Start auto-apply", symbol: "play") { confirm = true }
                        .disabled(book.capabilities?.submissionAvailable != true || book.capabilities?.matchingAvailable != true || !book.candidate.submissionConsent)
                        .accessibilityIdentifier("campaign.start")
                }
                Text("Runs for up to 30 days. Pausing stops queued work; it cannot recall applications already being submitted. Attempts may need answers or fail. Confirmed submissions appear separately.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                if let message { InlineMessage(text: message) }
            }.navigationTitle("Auto-apply").disabled(busy)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .confirmationDialog("Authorize up to \(maximum) application attempts?", isPresented: $confirm, titleVisibility: .visible) {
                    Button("Authorize auto-apply") { perform { try await book.startCampaign(maximum: maximum, daily: daily, threshold: threshold) } }
                } message: { Text("Uses your application allowance, with up to \(daily) attempts per day. Only qualifying, supported roles are eligible.") }
        }
    }
    private func perform(_ action: @escaping () async throws -> Void) {
        busy = true
        Task { defer { busy = false }; do { try await action() } catch { message = error.localizedDescription } }
    }
}

struct ConnectedPlansView: View {
    @Environment(NotebookModel.self) private var book
    @Environment(AppModel.self) private var model
    @Environment(PurchaseStore.self) private var purchases
    @State private var message: String?
    @State private var busy = false
    @State private var manage = false
    var body: some View {
        NotebookPage {
            NotebookHeading(chapter: "05 / Plan", title: "Application allowance", subtitle: "Your balance and the plans configured by the service.", tint: NotebookInk.pink)
            NotebookCard(tint: NotebookInk.mint) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("\(book.remaining)").font(Theme.sans(32, bold: true)).accessibilityIdentifier("connected.allowance")
                    Text("applications available").font(Theme.heading(18))
                    Text("Queued work reserves allowance. Unsubmitted failures are refunded; uncertain outcomes remain reserved.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                }
            }
            ForEach(book.catalog) { item in
                NotebookCard(tint: item.period == "month" ? NotebookInk.lavender : Theme.card) {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(item.period == "week" ? "Weekly" : item.period == "month" ? "Monthly" : "Top up").font(Theme.heading(20))
                        Text("\(item.credits / max(1, book.capabilities?.applicationCreditCost ?? 5)) applications\(item.period.map { " per \($0)" } ?? "")").font(Theme.sans(17, bold: true))
                        Text(item.kind == "subscription" ? "Each renewal adds allowance. Manage or cancel through Apple." : "One-time purchase. No subscription.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                        if let product = purchases.products.first(where: { $0.id == item.id }), !Configuration.connectedTest {
                            Text("\(product.displayName) · \(product.displayPrice)\(item.period.map { " per \($0)" } ?? " once")").font(Theme.sans(13, bold: true))
                            NotebookButton(title: "Buy · \(product.displayPrice)", symbol: "ticket") { Task { await purchases.buy(product, model: model) } }
                        }
                        #if DEBUG
                        if Configuration.connectedTest {
                            Button("Test checkout") { testPurchase(item) }.accessibilityIdentifier("connected.purchase.\(item.id)")
                        }
                        #endif
                    }
                }
            }
            if Configuration.connectedTest { Text("Test checkout exercises the server ledger using a receipt fixture. No Apple purchase or charge occurs.").font(Theme.sans(12)) }
            else if model.account?.billingAvailable != true { InlineMessage(text: "Purchases are not enabled on this server yet.") }
            else {
                Button("Restore purchases") { Task { await purchases.restore(model) } }
                Button("Manage subscription") { manage = true }
                Text("Weekly and monthly plans renew automatically at the price shown until cancelled in your Apple ID settings at least 24 hours before the period ends. Applications from each renewal stay in your account.")
                    .font(Theme.sans(11)).foregroundStyle(Theme.copy)
            }
            if let message = message ?? purchases.message { InlineMessage(text: message) }
            LegalLinks()
        }.navigationTitle("Your plan").disabled(busy || purchases.busy)
            .task { if !Configuration.connectedTest { await purchases.load(model) } }
            .manageSubscriptionsSheet(isPresented: $manage)
    }
    #if DEBUG
    private func testPurchase(_ item: CatalogProduct) {
        guard Configuration.connectedTest, let api = book.api else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                _ = try await api.write("v1/billing/transactions", method: "POST", body: ["signed_transaction": "fixture:\(item.id):\(UUID().uuidString)"], as: JSONValue.self)
                try await book.refreshConnection()
                message = "Test allowance added. No payment was made."
            } catch { message = error.localizedDescription }
        }
    }
    #endif
}

struct ResumePreview: UIViewRepresentable {
    let data: Data
    func makeUIView(context: Context) -> PDFView { let view = PDFView(); view.autoScales = true; return view }
    func updateUIView(_ view: PDFView, context: Context) { view.document = PDFDocument(data: data) }
}

struct ConnectedApplicationActions: View {
    @Environment(NotebookModel.self) private var book
    let record: ApplicationRecord
    @State private var answers: [String: String] = [:]
    @State private var busy = false
    @State private var message: String?
    @State private var pdf: Data?
    @State private var showPDF = false
    @State private var savingPDF = false
    @State private var retryConfirmation = false
    @FocusState private var answerEditing: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if !record.reason.isEmpty { InlineMessage(text: record.reason.replacingOccurrences(of: "_", with: " ")) }
            if let source = record.outcomeSource {
                Text(source == "user_reported" ? "Outcome reported by you" : "Outcome from verified integration").font(Theme.sans(12))
                if !record.outcomeNote.isEmpty { Text(record.outcomeNote).font(Theme.sans(13)) }
            }
            Text("Confirmation email: \(record.emailStatus.replacingOccurrences(of: "_", with: " "))").font(Theme.sans(12))
            if record.resumeAvailable {
                Button("View generated résumé") {
                    perform { pdf = try await book.api?.raw("v2/applications/\(record.id)/resume"); showPDF = pdf != nil }
                }.accessibilityIdentifier("connected.resume")
            }
            if record.serverState == "submitted" {
                Menu("Update outcome") {
                    Button("Interview") { perform { try await book.setOutcome(record.id, status: "interview") } }
                    Button("Offer") { perform { try await book.setOutcome(record.id, status: "offer") } }
                    Button("Rejected") { perform { try await book.setOutcome(record.id, status: "rejected") } }
                    Button("Withdrawn") { perform { try await book.setOutcome(record.id, status: "withdrawn") } }
                }.accessibilityIdentifier("connected.outcome")
            }
            if ["queued", "preparing"].contains(record.serverState) {
                Button("Cancel queued application", role: .destructive) { perform { try await book.cancelApplication(record.id) } }
            }
            if ["needs_user", "failed"].contains(record.serverState) {
                ForEach(record.questions) { question in
                    if question.supported {
                        if question.options.isEmpty {
                            TextField(question.required ? question.label : "\(question.label) (optional)", text: Binding(get: { answers[question.label] ?? "" }, set: { answers[question.label] = $0 }), axis: .vertical)
                                .focused($answerEditing)
                                .accessibilityIdentifier("answer.\(question.label)")
                        } else {
                            Picker(question.label, selection: Binding(get: { answers[question.label] ?? "" }, set: { answers[question.label] = $0 })) {
                                Text("Choose an answer").tag("")
                                ForEach(question.options, id: \.self) { Text($0).tag($0) }
                            }
                        }
                    } else { Text("\(question.label): complete this on the employer’s form.").font(Theme.sans(13)) }
                }
                if record.generation < 3 && !record.questions.contains(where: { !$0.supported }) {
                    Button("Retry with these answers") { retryConfirmation = true }.accessibilityIdentifier("connected.retry")
                        .disabled(record.questions.contains { $0.required && (answers[$0.label] ?? "").trimmingCharacters(in: .whitespaces).isEmpty })
                }
            }
            if record.serverState == "uncertain" { InlineMessage(text: "The employer’s response is unknown. This application will not be resubmitted automatically. Contact support with application ID \(record.id).") }
            if let url = URL(string: record.role.url), url.scheme == "https" { Link("Open employer’s job page", destination: url) }
            if let message { InlineMessage(text: message) }
        }.disabled(busy)
            .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { answerEditing = false }.accessibilityIdentifier("answer.dismiss-keyboard") } }
            .sheet(isPresented: $showPDF) {
                NavigationStack {
                    if let pdf {
                        ResumePreview(data: pdf).navigationTitle("Your résumé").navigationBarTitleDisplayMode(.inline)
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) { Button("Done") { showPDF = false } }
                                ToolbarItem(placement: .primaryAction) {
                                    ShareLink(item: ResumeFile(data: pdf, name: resumeBaseName + ".pdf"),
                                              preview: SharePreview(resumeBaseName, image: Image(systemName: "doc.richtext"))) {
                                        Label("Share", systemImage: "square.and.arrow.up")
                                    }.accessibilityIdentifier("connected.resume.share")
                                }
                                ToolbarItem(placement: .bottomBar) {
                                    Button("Save to Files") { savingPDF = true }.accessibilityIdentifier("connected.resume.save")
                                }
                            }
                            .fileExporter(isPresented: $savingPDF, document: PDFFile(data: pdf), contentType: .pdf, defaultFilename: resumeBaseName) { result in
                                switch result {
                                case .success: message = "Résumé saved to Files."
                                case .failure(let error): message = error.localizedDescription
                                }
                            }
                    }
                }
            }
            .confirmationDialog("Authorize another submission attempt?", isPresented: $retryConfirmation, titleVisibility: .visible) {
                Button("Authorize retry") { perform { try await book.retryApplication(record, answers: answers) } }
            } message: { Text("The previous attempt was refunded. This retry reserves one application again.") }
    }
    private var resumeBaseName: String {
        let company = record.role.company.filter { $0.isLetter || $0.isNumber || $0 == " " }.trimmingCharacters(in: .whitespaces)
        return company.isEmpty ? "JustHireMe resume" : "JustHireMe resume - \(company)"
    }
    private func perform(_ action: @escaping () async throws -> Void) {
        busy = true
        Task { defer { busy = false }; do { try await action() } catch { message = error.localizedDescription } }
    }
}

/// The generated résumé as a shareable PDF (AirDrop, Mail, Files) without leaving the app.
struct ResumeFile: Transferable {
    let data: Data
    let name: String
    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .pdf) { file in file.data }.suggestedFileName { $0.name }
    }
}

struct PDFFile: FileDocument {
    static var readableContentTypes: [UTType] { [.pdf] }
    var data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data() }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}
