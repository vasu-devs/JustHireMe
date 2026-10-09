import SwiftUI

struct DraftsView: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                JournalHeading(eyebrow: "Your application studio", title: "Make your next\nhello count.",
                               note: "Your story, ready for its next chapter.")
                if model.drafts.isEmpty {
                    VStack(alignment: .leading, spacing: 18) {
                        Image(systemName: "doc.text.below.ecg").font(.system(size: 42)).foregroundStyle(Theme.accent)
                        Text("A great application starts with a role.").font(Theme.display(29))
                        Text("Choose an opportunity, prepare a draft, then make it yours.").foregroundStyle(Theme.copy)
                        NavigationLink { JobsView() } label: {
                            Label("Choose a role", systemImage: "arrow.right").font(Theme.sans(15, bold: true))
                                .frame(maxWidth: .infinity).padding(16).foregroundStyle(Theme.buttonInk)
                                .background(Theme.accent, in: Capsule())
                        }.accessibilityIdentifier("drafts.choose-role")
                    }.padding(24).journalCard(tint: Theme.pink)
                }
                ForEach(model.drafts) { draft in
                    let job = model.jobs.first { $0.id == draft.jobId }
                    NavigationLink { DraftDetailView(draft: draft) } label: {
                        VStack(alignment: .leading, spacing: 15) {
                            HStack {
                                Label(job?.status == "saved" ? "Ready for your review" : (job?.status.capitalized ?? "Draft"), systemImage: "doc.text")
                                    .font(Theme.sans(12, bold: true)).foregroundStyle(Theme.accent)
                                Spacer()
                                Image(systemName: "arrow.up.right")
                            }
                            Text(job?.title ?? "Application draft").font(Theme.heading(22))
                            Text(job?.company ?? "Saved draft").foregroundStyle(Theme.copy)
                            JournalRule()
                            Text("Review, edit & share").font(Theme.sans(13, bold: true))
                        }.padding(22).journalCard(tint: Theme.green)
                    }.buttonStyle(.plain).accessibilityIdentifier("draft.\(draft.jobId)")
                }
                if model.isDemo {
                    Text("Preview drafts stay in this session. Share a copy to keep it.")
                        .font(Theme.sans(12)).foregroundStyle(Theme.copy)
                }
            }.padding(22).frame(maxWidth: 720).frame(maxWidth: .infinity)
        }.journalScreen().navigationTitle("Applications").navigationBarTitleDisplayMode(.inline)
            .refreshable { await model.reload() }
    }
}

struct DraftDetailView: View {
    @Environment(AppModel.self) private var model
    let draft: Draft
    @State private var text = ""
    @State private var editing = false
    @State private var message: String?
    @State private var confirmApplied = false
    @State private var busy = false
    private var job: Job? { model.jobs.first { $0.id == draft.jobId } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Eyebrow(text: model.isDemo ? "Sample application · ready for review" : "Your application · ready for review")
                Text(job?.title ?? "Your application").font(Theme.display(35))
                Text(job?.company ?? "Application studio").font(Theme.heading(18)).foregroundStyle(Theme.accent)
                HStack(spacing: 8) {
                    stage("Prepare", complete: true)
                    stage("Review", complete: model.draftEdits[draft.id] != nil)
                    stage("Applied", complete: ["applied", "interviewing", "offer"].contains(job?.status ?? ""))
                }
                HStack {
                    Text("Your draft").font(Theme.heading(21))
                    Spacer()
                    Button(editing ? "Save changes" : "Edit draft") {
                        if editing {
                            do { try model.saveEdit(text, for: draft); editing = false; message = model.isDemo ? "Changes saved for this preview." : "Changes saved on this device." }
                            catch { message = error.localizedDescription }
                        } else { editing = true }
                    }.font(Theme.sans(14, bold: true)).accessibilityIdentifier("draft.edit")
                }
                if editing {
                    TextEditor(text: $text).frame(minHeight: 440).scrollContentBackground(.hidden)
                        .padding(16).journalCard().accessibilityLabel("Application text").accessibilityIdentifier("draft.editor")
                    Text("Save changes before leaving this screen.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                } else {
                    Text(text).font(Theme.sans(16)).lineSpacing(6).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(22).journalCard()
                }
                InlineMessage(text: model.isDemo ? "This sample uses your preview profile. Check every statement and personalize it before sharing." : "Review every name, qualification, date, and claim before sharing. Edits are saved on this device; export a copy to keep elsewhere.")
                if let message { Text(message).font(Theme.sans(14)).foregroundStyle(Theme.accent).accessibilityIdentifier("draft.message") }
                if let job, job.status == "saved" {
                    Button("I’ve submitted this application") { confirmApplied = true }
                        .font(Theme.sans(15, bold: true)).accessibilityIdentifier("draft.mark-applied")
                        .disabled(busy || editing)
                } else if let job {
                    Label("Status: \(job.status.capitalized)", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(Theme.accent).accessibilityIdentifier("draft.status")
                }
            }.padding(22).frame(maxWidth: 720).frame(maxWidth: .infinity)
        }.journalScreen().navigationTitle("Review application").navigationBarTitleDisplayMode(.inline)
            .scrollDismissesKeyboard(.interactively)
            .task { text = model.text(for: draft) }
            .safeAreaInset(edge: .bottom) {
                ShareLink(item: text) {
                    Label("Share application", systemImage: "square.and.arrow.up").font(Theme.sans(15, bold: true))
                        .foregroundStyle(Theme.buttonInk).frame(maxWidth: .infinity).padding(17)
                        .background(Theme.accent, in: Capsule())
                }.disabled(editing).accessibilityIdentifier("draft.share")
                    .padding(.horizontal, 22).padding(.vertical, 12).background(Theme.chrome)
            }
            .confirmationDialog("Already sent your application?", isPresented: $confirmApplied, titleVisibility: .visible) {
                Button("Mark as applied") { Task {
                    guard let job else { return }
                    busy = true
                    defer { busy = false }
                    do { try await model.update(job, status: "applied"); message = "Nice work. Your role is now marked as applied." }
                    catch { message = error.localizedDescription }
                } }
            } message: { Text("This updates your tracker. JustHireMe does not send anything to the employer.") }
    }

    private func stage(_ title: String, complete: Bool) -> some View {
        Label(title, systemImage: complete ? "checkmark.circle.fill" : "circle")
            .font(Theme.sans(11, bold: true)).foregroundStyle(complete ? Theme.accent : Theme.copy)
            .frame(maxWidth: .infinity).padding(.vertical, 12).background(Theme.green.opacity(0.18), in: Capsule())
    }
}
