import SwiftUI

struct RecommendedRolesView: View {
    @Environment(NotebookModel.self) private var book
    @State private var remoteOnly = false
    @State private var automation = false
    private var visible: [SuggestedRole] {
        book.roles.filter { !remoteOnly || $0.location.localizedCaseInsensitiveContains("Remote") }.sorted { $0.score(book.profile) > $1.score(book.profile) }
    }
    var body: some View {
        NotebookPage {
            NotebookHeading(chapter: "02 / Jobs", title: "Job matches", subtitle: "Roles that match your skills and preferences.", tint: NotebookInk.mint)
            HStack {
                NotebookTag(text: "\(book.remaining) applications left", tint: NotebookInk.butter)
                Spacer()
                Button { automation = true } label: { Label("Auto-apply", systemImage: "slider.horizontal.3").font(Theme.sans(12, bold: true)) }
                    .accessibilityIdentifier("matches.automation")
            }
            Toggle("Remote roles only", isOn: $remoteOnly).font(Theme.sans(13)).tint(Theme.accent)
            if visible.isEmpty {
                NotebookCard(tint: NotebookInk.sky) {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("No matches yet").font(Theme.display(28))
                        Text(book.isConnected ? "Matches may still be processing. Check your saved profile and matching consent, then refresh. Only current eligible jobs above your relevance threshold appear." : "Complete your profile to be ready for personalized recommendations when the service is connected.").font(Theme.sans(14)).foregroundStyle(Theme.copy)
                        NavigationLink("Open my profile") { NotebookProfileView() }
                    }
                }
            }
            ForEach(Array(visible.enumerated()), id: \.element.id) { index, role in
                NavigationLink(value: role) { RecommendedRoleCard(role: role, index: index) }
                    .buttonStyle(.plain).accessibilityIdentifier("match.\(role.id)")
            }
            if book.nextFeedOffset != nil {
                Button("Load more jobs") { Task { do { try await book.loadMoreRoles() } catch { book.connectionMessage = error.localizedDescription } } }
            }
            if let message = book.connectionMessage { InlineMessage(text: message) }
            Text(book.isPreview ? "Sample recommendations. Scores show skill overlap, not your chance of being hired." : "Recommendations come from the shared job service. No scraper setup is needed.")
                .font(Theme.sans(11)).foregroundStyle(Theme.copy)
        }.navigationTitle("For you")
            .navigationDestination(for: SuggestedRole.self) { RecommendedRoleDetail(role: $0) }
            .sheet(isPresented: $automation) { if book.isConnected { ConnectedAutomationView() } else { AutomationSettingsView() } }
            .refreshable { do { try await book.refreshConnection() } catch { book.connectionMessage = error.localizedDescription } }
    }
}

struct RecommendedRoleCard: View {
    @Environment(NotebookModel.self) private var book
    let role: SuggestedRole
    var index = 0
    var body: some View {
        NotebookCard(tint: NotebookInk.color(index)) {
            VStack(alignment: .leading, spacing: 17) {
                HStack {
                    Text(String(role.company.prefix(1))).font(Theme.display(28)).frame(width: 43, height: 46)
                        .background(Theme.card.opacity(0.75), in: RoundedRectangle(cornerRadius: 8)).rotationEffect(.degrees(-5))
                    Text(role.company).font(Theme.sans(13, bold: true))
                    Spacer()
                    Text("\(role.score(book.profile))% \(role.relevance == nil ? "skill match" : "relevance")").font(Theme.sans(12))
                }
                Text(role.title).font(Theme.heading(21))
                Text(role.type.isEmpty ? role.location : "\(role.location) · \(role.type)").font(Theme.sans(13)).foregroundStyle(Theme.copy)
                if let date = role.lastChecked { Text("Checked \(date.formatted(date: .omitted, time: .shortened))").font(Theme.sans(11)).foregroundStyle(Theme.copy) }
                if !role.salary.isEmpty { Text(role.salary).font(Theme.sans(12)).foregroundStyle(Theme.copy) }
                CrayonStroke(color: Theme.ink.opacity(0.08)).frame(height: 7)
                HStack {
                    Text(book.applications.contains { $0.role.id == role.id } ? "View application" : "View role").font(Theme.sans(13, bold: true))
                    Spacer(); Image(systemName: "arrow.up.right")
                }
            }
        }
    }
}

struct RecommendedRoleDetail: View {
    @Environment(NotebookModel.self) private var book
    let role: SuggestedRole
    @State private var submitted: ApplicationRecord?
    @State private var showApplication = false
    @State private var showPlan = false
    @State private var message: String?
    private var existing: ApplicationRecord? { book.applications.first { $0.role.id == role.id } }
    var body: some View {
        NotebookPage {
            RecommendedRoleCard(role: role, index: 1)
            NotebookCard(ruled: true) {
                VStack(alignment: .leading, spacing: 17) {
                    Text(role.relevance == nil ? "Skills match" : "Skills mentioned in the job").font(Theme.heading(21))
                    Text(role.relevance == nil ? "\(role.matched(book.profile).count) of \(role.requirements.count) requested skills are in your profile." : "Text matches from the job description. The server’s relevance score is separate and is not a hiring probability.").font(Theme.sans(14)).foregroundStyle(Theme.copy)
                    ForEach(role.requirements, id: \.self) { skill in
                        HStack {
                            Image(systemName: role.matched(book.profile).contains(skill) ? "checkmark.circle" : "circle.dashed")
                            Text(skill).font(Theme.sans(14))
                            Spacer()
                            if !role.matched(book.profile).contains(skill) { Text("Not in profile").font(Theme.sans(10)).foregroundStyle(Theme.copy) }
                        }
                    }
                }
            }
            NotebookCard {
                VStack(alignment: .leading, spacing: 14) {
                    Text("About the role").font(Theme.heading(19))
                    Text(role.description).font(Theme.sans(15)).lineSpacing(5).foregroundStyle(Theme.copy)
                    Label("Uses your latest profile", systemImage: "book.closed").font(Theme.sans(12))
                    Text("One application from your allowance. If a role needs extra answers, it belongs in Needs attention.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                }
            }
            if let message { InlineMessage(text: message) }
        }.navigationTitle(role.company)
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 9) {
                    NotebookButton(title: existing == nil ? "Apply now" : "View application", symbol: existing == nil ? "paperplane" : "arrow.right") {
                        if let existing { submitted = existing; showApplication = true }
                        else if book.remaining == 0 { showPlan = true }
                        else {
                            Task {
                                do {
                                    if book.isConnected { submitted = try await book.submitConnected(role) }
                                    else { submitted = try book.apply(role) }
                                    showApplication = true
                                } catch { message = error.localizedDescription }
                            }
                        }
                    }.disabled(book.loadingApplicationIDs.contains(role.id) || (existing == nil && book.isConnected && (!role.canApply || book.capabilities?.submissionAvailable != true)))
                        .accessibilityIdentifier("match.apply")
                    Text(book.isPreview ? "Preview only · 1 sample application · nothing is sent" : role.canApply ? "Reserves 1 application · queued first, then confirmed" : "Automatic submission is unavailable for this employer")
                        .font(Theme.sans(10)).foregroundStyle(Theme.copy)
                }.padding(.horizontal, 22).padding(.vertical, 12).background(Theme.chrome)
            }
            .navigationDestination(isPresented: $showApplication) { if let submitted { ApplicationRecordView(record: submitted) } }
            .sheet(isPresented: $showPlan) { NavigationStack { Group { if book.isConnected { ConnectedPlansView() } else { ApplicationPlansView() } }.toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showPlan = false } } } } }
    }
}

struct AutomationSettingsView: View {
    @Environment(NotebookModel.self) private var book
    @Environment(\.dismiss) private var dismiss
    @State private var result: String?
    var body: some View {
        @Bindable var book = book
        NavigationStack {
            NotebookPage {
                NotebookHeading(chapter: "Jobs / Preferences", title: "Auto-apply settings", subtitle: "Set your roles, location and daily limit.", tint: NotebookInk.butter)
                NotebookCard(tint: NotebookInk.butter) {
                    VStack(alignment: .leading, spacing: 18) {
                        Toggle("Enable auto-apply preview", isOn: $book.autoEnabled).font(Theme.sans(15, bold: true))
                            .disabled(!book.isPreview).accessibilityIdentifier("auto.enable")
                        TextField("Eligible role titles, comma separated", text: $book.profile.targetRoles, axis: .vertical)
                        TextField("Preferred location", text: $book.profile.location)
                        Stepper("Minimum skill overlap: \(book.autoMinimum)%", value: $book.autoMinimum, in: 50...100, step: 5).font(Theme.sans(13))
                        Stepper("Up to \(book.autoDailyLimit) per day", value: $book.autoDailyLimit, in: 1...5).font(Theme.sans(13))
                    }
                }
                Text("Only these titles and this location qualify. Duplicate applications are skipped, and your allowance is never exceeded. Turn this off at any time.").font(Theme.sans(13)).foregroundStyle(Theme.copy)
                NotebookButton(title: "Run a preview", symbol: "play") {
                    do {
                        let count = try book.runAutomationPreview()
                        result = count == 0 ? "No eligible roles within today’s limit. Nothing was submitted." : "\(count) sample applications added to your tracker. No employers were contacted."
                    } catch { result = error.localizedDescription }
                }.disabled(!book.autoEnabled || !book.isPreview).accessibilityIdentifier("auto.run")
                if let result { InlineMessage(text: result).accessibilityIdentifier("auto.result") }
                Text("This preview runs only when you tap. Continuous background applications need the connected service.").font(Theme.sans(11)).foregroundStyle(Theme.copy)
            }.navigationTitle("Auto-apply")
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}
