import SwiftUI
import UniformTypeIdentifiers

private struct ExportDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.json] }
    var data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data() }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}

struct ProfileView: View {
    @Environment(AppModel.self) private var model
    @State private var profile = CandidateProfile()
    @State private var skills = ""
    @State private var busy = false
    @State private var message: String?
    @State private var confirmDelete = false
    @State private var exportDocument: ExportDocument?
    @State private var exportPresented = false

    var body: some View {
        Form {
            Section {
                Text("Start with your story.").font(.system(.title2, design: .serif))
                Text("Your real experience is the foundation of every application.").font(.subheadline).foregroundStyle(.secondary)
            }
            Section("About you") {
                TextField("Full name", text: $profile.name).textContentType(.name)
                    .accessibilityIdentifier("profile.name")
                TextField("Professional headline", text: $profile.headline)
                TextField("City or region", text: $profile.location)
                TextField("Skills, separated by commas", text: $skills, axis: .vertical)
            }
            Section("Experience, education, and achievements") {
                TextEditor(text: $profile.experience).frame(minHeight: 180).accessibilityLabel("Your experience")
                Text("Include the facts you want in your résumé: roles, dates, projects, education, and measurable results.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Your data, your choice") {
                Toggle("Allow AI application drafting", isOn: $profile.aiConsent)
                    .accessibilityIdentifier("profile.ai-consent")
                Text("When you request a draft, your profile and that job description are shared with Anthropic to generate it. Your profile and drafts are stored in your JustHireMe cloud account. Turn this off to stop future AI requests; data already sent is subject to the provider’s retention policy.")
                    .font(.footnote).foregroundStyle(.secondary)
                Link("Anthropic privacy policy", destination: URL(string: "https://www.anthropic.com/legal/privacy")!)
                LegalLinks()
            }
            Section {
                Button("Save profile") { Task { await save() } }.disabled(busy || model.isDemo || model.account == nil)
                    .accessibilityIdentifier("profile.save")
                if model.isDemo { Text("This is a sample profile. Sign in to save your own.").font(.caption) }
                if let message { Text(message).font(.callout).foregroundStyle(.secondary) }
            }
            Section("Account") {
                Button("Export my data") { Task { await export() } }.disabled(busy || model.isDemo)
                Button("Sign out") { Task { await model.signOut() } }.disabled(busy)
                Button("Delete account", role: .destructive) { confirmDelete = true }.disabled(busy || model.isDemo)
                Text("Deleting your account removes your profile, jobs, and drafts. Minimal purchase records are retained for billing. Cancel any Apple subscription separately before deleting.")
                    .font(.caption).foregroundStyle(.secondary)
                Link("Manage Apple subscriptions", destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
            }
        }.navigationTitle("Profile")
            .task(id: model.isDemo ? "demo" : model.account?.id ?? "") {
                profile = model.profile
                skills = profile.skills.joined(separator: ", ")
            }
            .confirmationDialog("Permanently delete your account?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete my account and data", role: .destructive) { Task { await delete() } }
            } message: { Text("Your saved jobs, drafts, profile, and remaining credits will be removed. Your Apple subscription must be cancelled separately.") }
            .fileExporter(isPresented: $exportPresented, document: exportDocument, contentType: .json,
                          defaultFilename: "justhireme-export") { result in
                exportDocument = nil
                if case .failure(let error) = result { message = error.localizedDescription }
            }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        profile.skills = skills.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        do { try await model.saveProfile(profile); message = "Profile saved." }
        catch { message = error.localizedDescription }
    }

    private func export() async {
        busy = true
        defer { busy = false }
        do {
            exportDocument = ExportDocument(data: try await model.api.raw("v1/export"))
            exportPresented = true
        } catch { message = error.localizedDescription }
    }

    private func delete() async {
        busy = true
        defer { busy = false }
        do {
            _ = try await model.api.raw("v1/account", method: "DELETE")
            await model.signOut()
        } catch { message = error.localizedDescription }
    }
}
