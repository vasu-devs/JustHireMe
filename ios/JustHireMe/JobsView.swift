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
    private let filters = ["all", "saved", "applied", "interviewing", "offer"]
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
                    Eyebrow(text: "Make your next move")
                    Spacer()
                    Label(model.isDemo ? "Demo" : "\(model.account?.balance ?? 0) credits", systemImage: "sparkles")
                        .font(.caption.weight(.semibold)).foregroundStyle(Theme.accent)
                }
                Text("Good work\nstarts here.").font(.system(.largeTitle, design: .serif, weight: .medium))
                HStack(spacing: 12) {
                    metric("In your pipeline", value: model.jobs.filter { $0.status != "archived" }.count)
                    metric("Interviews", value: model.jobs.filter { $0.status == "interviewing" }.count)
                }
                HStack {
                    Text("Your opportunities").font(.title3.weight(.bold))
                    Spacer()
                    Button { sheet = .add } label: { Image(systemName: "plus").fontWeight(.semibold).padding(8) }
                        .buttonStyle(.bordered).accessibilityLabel("Add a job")
                        .accessibilityIdentifier("jobs.add")
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(filters, id: \.self) { value in
                            Button(value.capitalized) { filter = value }
                                .font(.subheadline.weight(.medium)).padding(.horizontal, 16).padding(.vertical, 10)
                                .background(filter == value ? Theme.accent : Theme.card, in: Capsule())
                                .foregroundStyle(filter == value ? Color.white : Color.primary)
                                .accessibilityIdentifier("filter.\(value)")
                        }
                    }
                }
                if model.isLoading && model.jobs.isEmpty { ProgressView("Loading your workspace…").frame(maxWidth: .infinity) }
                if let message = model.message {
                    InlineMessage(text: message)
                    Button("Retry") { Task { model.message = nil; await model.reload() } }
                }
                if visibleJobs.isEmpty && !model.isLoading {
                    ContentUnavailableView("Room for your next role", systemImage: "tray",
                        description: Text("Add a job description to track an opportunity and prepare an application."))
                }
                LazyVStack(spacing: 14) {
                    ForEach(visibleJobs) { job in
                        NavigationLink(value: job) { JobCard(job: job, skills: model.profile.skills) }
                            .buttonStyle(.plain).accessibilityIdentifier("job.\(job.id)")
                    }
                }
            }.padding(22).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }
        .background(Theme.background).navigationTitle("Workspace").navigationBarTitleDisplayMode(.inline)
        .searchable(text: $search, prompt: "Find a role or company")
        .refreshable { await model.reload() }
        .navigationDestination(for: Job.self) { JobDetailView(job: $0) }
        .sheet(item: $sheet) { _ in AddJobView() }
    }

    private func metric(_ label: String, value: Int) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(value.formatted()).font(.system(.largeTitle, design: .rounded, weight: .semibold))
            Text(label).font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 22))
    }
}

struct JobCard: View {
    let job: Job
    let skills: [String]
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                Text(String(job.company.prefix(1))).font(.title2.weight(.bold))
                    .frame(width: 46, height: 46).background(Theme.accent.opacity(0.10), in: RoundedRectangle(cornerRadius: 14))
                    .foregroundStyle(Theme.accent)
                VStack(alignment: .leading, spacing: 5) {
                    Text(job.title).font(.headline)
                    Text(job.company).font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                Image(systemName: "arrow.up.right").foregroundStyle(.secondary).accessibilityHidden(true)
            }
            if !job.location.isEmpty { Label(job.location, systemImage: "mappin.and.ellipse").font(.caption).foregroundStyle(.secondary) }
            Divider()
            HStack {
                Text(job.status.capitalized).font(.caption.weight(.semibold)).foregroundStyle(Theme.accent)
                Spacer()
                let matches = job.skillMatches(skills)
                Text(matches.isEmpty ? "Explore this role" : "\(matches.count) skills mentioned")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.padding(20).background(Theme.card, in: RoundedRectangle(cornerRadius: 22))
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
                if model.isDemo { Text("Sign in to save your own opportunities. Demo changes are temporary.").foregroundStyle(.secondary) }
                Section("The opportunity") {
                    TextField("Job title", text: $title).accessibilityIdentifier("job.form.title")
                    TextField("Company", text: $company).accessibilityIdentifier("job.form.company")
                    TextField("Location", text: $location)
                    TextField("Job URL (optional)", text: $url).keyboardType(.URL).textInputAutocapitalization(.never)
                }
                Section("Paste the job description") {
                    TextEditor(text: $description).frame(minHeight: 200).accessibilityLabel("Job description")
                        .accessibilityIdentifier("job.form.description")
                    Text("At least 40 characters. The app saves this text; it does not scrape the link.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let error { Text(error).foregroundStyle(.red) }
            }
            .navigationTitle("Add an opportunity").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .accessibilityIdentifier("job.form.save")
                        .disabled(busy || title.trimmingCharacters(in: .whitespaces).isEmpty || company.isEmpty || description.count < 40)
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
                job = Job(id: UUID().uuidString, title: title, company: company, location: location, url: "",
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
                        Text(matches.joined(separator: " · ")).font(.headline)
                        Text("Exact skill mentions from the job description, not a prediction of hiring success.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("The role").font(.title2.weight(.semibold))
                    Text(current.description).foregroundStyle(.secondary).textSelection(.enabled)
                }
                if let url = URL(string: current.url), url.scheme == "https" {
                    Link(destination: url) { Label("Open original posting", systemImage: "arrow.up.right.square") }
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("Make it personal.").font(.system(.title2, design: .serif))
                    Text("Create a résumé, cover letter, and outreach draft using the experience in your profile. Review every detail before sharing.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    ActionButton(title: "Prepare application · \(model.account?.tailorCost ?? 5) credits", busy: busy) { confirm = true }
                        .disabled(model.isDemo || model.account?.tailoringAvailable != true)
                        .accessibilityIdentifier("job.tailor")
                    if model.isDemo { Text("Application drafting is available after sign-in.").font(.caption) }
                    else if model.account?.tailoringAvailable != true { Text("Drafting is not available on this server yet.").font(.caption) }
                    if let message { InlineMessage(text: message) }
                }.padding(22).background(Theme.card, in: RoundedRectangle(cornerRadius: 22))
            }.padding(22).frame(maxWidth: 760).frame(maxWidth: .infinity)
        }.background(Theme.background).navigationTitle(current.company).navigationBarTitleDisplayMode(.inline)
            .confirmationDialog("Create an application draft?", isPresented: $confirm, titleVisibility: .visible) {
                Button("Use \(model.account?.tailorCost ?? 5) credits") { Task { await generate() } }
            } message: {
                Text("Your profile and this job description will be sent to Anthropic. Failed drafts return your credits. You control when anything is shared with an employer.")
            }
    }

    private func generate() async {
        let accountID = model.account?.id
        busy = true
        defer { busy = false }
        do {
            let draft = try await model.api.write("v1/jobs/\(job.id)/tailor", method: "POST", body: [:],
                                                  as: Draft.self, key: requestKey)
            guard model.account?.id == accountID, model.isSignedIn else { return }
            if !model.drafts.contains(where: { $0.id == draft.id }) { model.drafts.insert(draft, at: 0) }
            message = "Your application is ready in Drafts. Review it before sharing."
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
