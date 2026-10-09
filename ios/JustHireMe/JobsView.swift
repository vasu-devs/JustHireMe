import SwiftUI

private enum JobSheet: String, Identifiable {
    case add
    var id: String { rawValue }
}

struct JobsView: View {
    @Environment(AppModel.self) private var model
    @State private var search = ""
    @State private var filter = "all"
    @State private var sheet: JobSheet?
    private let filters = ["all", "saved", "applied", "interviewing", "offer", "archived"]
    private var visibleJobs: [Job] {
        model.jobs.filter {
            (filter == "all" || $0.status == filter) &&
            (search.isEmpty || "\($0.title) \($0.company)".localizedCaseInsensitiveContains(search))
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack {
                    Eyebrow(text: "Opportunities, thoughtfully collected")
                    Spacer()
                    Label(model.isDemo ? "Demo" : "\(model.account?.balance ?? 0) credits", systemImage: "sparkles")
                        .font(.caption.weight(.semibold)).foregroundStyle(Theme.accent)
                }
                Text("Find your kind\nof work.").font(Theme.display(38))
                HStack {
                    Text("\(visibleJobs.count) roles in view").font(Theme.heading())
                    Spacer()
                    Button { sheet = .add } label: { Label("Add role", systemImage: "plus").font(Theme.sans(13, bold: true)).padding(5) }
                        .buttonStyle(.bordered).accessibilityLabel("Add a job")
                        .accessibilityIdentifier("jobs.add")
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(filters, id: \.self) { value in
                            Button(value.capitalized) { filter = value }
                                .font(.subheadline.weight(.medium)).padding(.horizontal, 16).padding(.vertical, 10)
                                .background(filter == value ? Theme.accent : Theme.card, in: Capsule())
                                .foregroundStyle(filter == value ? Theme.buttonInk : Theme.ink)
                                .accessibilityIdentifier("filter.\(value)")
                                .accessibilityAddTraits(filter == value ? .isSelected : [])
                        }
                    }
                }
                if model.isLoading && model.jobs.isEmpty { ProgressView("Loading your workspace…").frame(maxWidth: .infinity) }
                if let message = model.message {
                    InlineMessage(text: message)
                    Button("Retry") { Task { model.message = nil; await model.reload() } }
                }
                if visibleJobs.isEmpty && !model.isLoading {
                    ContentUnavailableView {
                        Label(search.isEmpty ? "A little room for possibility" : "No matching roles", systemImage: "magnifyingglass")
                    } description: {
                        Text(search.isEmpty ? "Save an opportunity here, or choose another status." : "Try another title or company.")
                    } actions: {
                        Button(search.isEmpty && filter == "all" ? "Add your first role" : "Show all roles") {
                            if search.isEmpty && filter == "all" { sheet = .add } else { search = ""; filter = "all" }
                        }
                    }
                }
                LazyVStack(spacing: 14) {
                    ForEach(Array(visibleJobs.enumerated()), id: \.element.id) { index, job in
                        NavigationLink(value: job) { JobCard(job: job, skills: model.profile.skills, index: index) }
                            .buttonStyle(.plain).accessibilityIdentifier("job.\(job.id)")
                    }
                }
            }.padding(22).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }
        .journalScreen().navigationTitle("Roles").navigationBarTitleDisplayMode(.inline)
        .searchable(text: $search, prompt: "Find a role or company")
        .refreshable { await model.reload() }
        .navigationDestination(for: Job.self) { JobDetailView(job: $0) }
        .sheet(item: $sheet) { _ in AddJobView() }
    }

    private func metric(_ label: String, value: Int) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(value.formatted()).font(Theme.mono(28))
            Text(label).font(Theme.sans(12)).foregroundStyle(Theme.copy)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .journalCard(tint: label == "Interviews" ? Theme.yellow : Theme.blue)
    }
}

struct JobCard: View {
    let job: Job
    let skills: [String]
    var index = 0
    private var tint: Color { [Theme.blue, Theme.pink, Theme.green][index % 3] }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                Text(String(job.company.prefix(1))).font(Theme.heading(20))
                    .frame(width: 42, height: 42).background(tint.opacity(0.7), in: RoundedRectangle(cornerRadius: 13))
                    .foregroundStyle(Theme.ink)
                VStack(alignment: .leading, spacing: 5) {
                    Text(job.company.uppercased()).font(Theme.mono(10)).foregroundStyle(Theme.faint)
                    Text(job.title).font(Theme.heading(18))
                }
                Spacer(minLength: 0)
                Image(systemName: "arrow.up.right").foregroundStyle(Theme.copy).accessibilityHidden(true)
            }
            if !job.location.isEmpty { Label(job.location, systemImage: "mappin.and.ellipse").font(Theme.sans(12)).foregroundStyle(Theme.copy) }
            JournalRule()
            HStack {
                Text(job.status.capitalized).font(.caption.weight(.semibold)).foregroundStyle(Theme.accent)
                Spacer()
                let matches = job.skillMatches(skills)
                Text(matches.isEmpty ? "Explore this role" : "\(matches.count) skills mentioned")
                    .font(Theme.sans(12)).foregroundStyle(Theme.copy)
            }
        }.padding(18).journalCard(tint: tint)
    }
}

struct AddJobView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var company = ""
    @State private var location = ""
    @State private var url = ""
    @State private var description = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                if model.isDemo { Text("Try adding a role. Preview changes last for this session.").foregroundStyle(Theme.copy) }
                Section("The opportunity") {
                    TextField("Job title", text: $title).accessibilityIdentifier("job.form.title")
                    TextField("Company", text: $company).accessibilityIdentifier("job.form.company")
                    TextField("Location", text: $location)
                    TextField("Job URL (optional)", text: $url).keyboardType(.URL).textInputAutocapitalization(.never)
                }.listRowBackground(Theme.card)
                Section("Paste the job description") {
                    TextEditor(text: $description).frame(minHeight: 200).accessibilityLabel("Job description")
                        .accessibilityIdentifier("job.form.description")
                    Text("Paste at least 40 characters from the original posting.")
                        .font(Theme.sans(12)).foregroundStyle(Theme.copy)
                }.listRowBackground(Theme.card)
                if let error { Text(error).foregroundStyle(.red) }
            }
            .scrollContentBackground(.hidden).journalScreen()
            .navigationTitle("Add an opportunity").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .accessibilityIdentifier("job.form.save")
                        .disabled(busy || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || company.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || description.trimmingCharacters(in: .whitespacesAndNewlines).count < 40)
                }
            }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let job: Job
            if model.isDemo {
                job = Job(id: UUID().uuidString, title: title, company: company, location: location, url: url,
                          description: description, status: "saved")
            } else {
                job = try await model.api.write("v1/jobs", method: "POST", body: ["title": title, "company": company,
                    "location": location, "url": url, "description": description], as: Job.self)
            }
            model.jobs.insert(job, at: 0)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

struct JobDetailView: View {
    @Environment(AppModel.self) private var model
    let job: Job
    @State private var busy = false
    @State private var message: String?
    @State private var requestKey = UUID()
    @State private var confirm = false
    @State private var openedDraft: Draft?
    @State private var showDraft = false
    @State private var showPlans = false
    @State private var showProfile = false
    private var current: Job { model.jobs.first { $0.id == job.id } ?? job }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                JobCard(job: current, skills: model.profile.skills)
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow(text: "Keep your momentum")
                    Menu {
                        ForEach(["saved", "applied", "interviewing", "offer", "archived"], id: \.self) { status in
                            Button(status.capitalized) { Task {
                                do { try await model.update(current, status: status) }
                                catch { message = error.localizedDescription }
                            } }
                            .accessibilityIdentifier("status.\(status)")
                        }
                    } label: {
                        Label("Status: \(current.status.capitalized)", systemImage: "chevron.up.chevron.down")
                            .frame(maxWidth: .infinity, alignment: .leading).padding()
                    }.buttonStyle(.bordered).accessibilityIdentifier("job.status")
                }
                let matches = current.skillMatches(model.profile.skills)
                if !matches.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Eyebrow(text: "Your skills in this role")
                        Text(matches.joined(separator: " · ")).font(Theme.heading(18))
                        Text("Exact skill mentions from the job description, not a prediction of hiring success.")
                            .font(Theme.sans(12)).foregroundStyle(Theme.copy)
                    }
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("The role").font(Theme.heading(23))
                    Text(current.description).foregroundStyle(Theme.copy).textSelection(.enabled)
                }
                if let url = URL(string: current.url), url.scheme == "https" {
                    Link(destination: url) { Label("Open original posting", systemImage: "arrow.up.right.square") }
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("A thoughtful first impression.").font(Theme.display(29))
                    Label("Profile summary, cover letter & outreach", systemImage: "doc.text")
                    Text(model.isDemo ? "Try the full flow with a sample draft built from your preview profile. No AI request or real charge." : "Use your experience to prepare a first draft. Review and edit it before sharing.")
                        .font(Theme.sans(14)).foregroundStyle(Theme.copy)
                }.padding(22).journalCard(tint: Theme.pink)
                if let message { InlineMessage(text: message).accessibilityIdentifier("job.message") }
                if !model.isDemo && !model.profile.aiConsent {
                    NavigationLink("Allow drafting in your profile") { ProfileView() }
                }
            }.padding(22).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }.journalScreen().navigationTitle(current.company).navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 8) {
                    ActionButton(title: actionTitle, busy: busy) {
                        if let draft = model.drafts.first(where: { $0.jobId == job.id }) { openedDraft = draft; showDraft = true }
                        else if !model.isDemo && !model.profile.aiConsent { showProfile = true }
                        else if model.balance < model.tailorCost { showPlans = true }
                        else if model.isDemo { Task { await generate() } }
                        else { confirm = true }
                    }.accessibilityIdentifier("job.tailor")
                        .disabled(!model.isDemo && model.account?.tailoringAvailable != true)
                    Text(model.isDemo ? "\(model.balance) demo credits available · nothing is sent" : "You review it. You decide when to send.")
                        .font(Theme.sans(11)).foregroundStyle(Theme.copy)
                }.padding(.horizontal, 22).padding(.vertical, 12).background(Theme.chrome)
            }
            .navigationDestination(isPresented: $showDraft) { if let openedDraft { DraftDetailView(draft: openedDraft) } }
            .navigationDestination(isPresented: $showProfile) { ProfileView() }
            .sheet(isPresented: $showPlans) { NavigationStack { PlansView().toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showPlans = false } } } } }
            .confirmationDialog("Create an application draft?", isPresented: $confirm, titleVisibility: .visible) {
                Button("Use \(model.account?.tailorCost ?? 5) credits") { Task { await generate() } }
            } message: {
                Text("Your profile and this job description will be sent to Anthropic. Failed drafts return your credits. You control when anything is shared with an employer.")
            }
    }

    private var actionTitle: String {
        if model.drafts.contains(where: { $0.jobId == job.id }) { return "Open your application" }
        if !model.isDemo && !model.profile.aiConsent { return "Complete your profile to continue" }
        if model.balance < model.tailorCost { return "Get credits to continue" }
        if !model.isDemo && model.account?.tailoringAvailable != true { return "Drafting is not available yet" }
        return "\(model.isDemo ? "Preview" : "Prepare") application · \(model.tailorCost) credits"
    }

    private func generate() async {
        let accountID = model.account?.id
        busy = true
        defer { busy = false }
        do {
            if model.isDemo {
                openedDraft = try model.previewApplication(for: current)
                showDraft = true
                return
            }
            let draft = try await model.api.write("v1/jobs/\(job.id)/tailor", method: "POST", body: [:],
                                                  as: Draft.self, key: requestKey)
            guard model.account?.id == accountID, model.isSignedIn else { return }
            if !model.drafts.contains(where: { $0.id == draft.id }) { model.drafts.insert(draft, at: 0) }
            openedDraft = draft
            showDraft = true
            requestKey = UUID()
            await model.reload()
        } catch {
            message = error.localizedDescription
            // A failed/refunded operation explicitly permits a new attempt. Network errors retain
            // the same key, preventing a lost HTTP response from charging the customer twice.
            if message?.contains("returned") == true { requestKey = UUID() }
            await model.reload()
        }
    }
}
