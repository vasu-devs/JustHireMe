import Foundation
import Observation

@MainActor @Observable
final class AppModel {
    let api = APIClient()
    let notebook = NotebookModel()
    var isDemo = false
    var isSignedIn = false
    var isLoading = false
    var account: Account?
    var jobs: [Job] = []
    var drafts: [Draft] = []
    var ledger: [LedgerEntry] = []
    var message: String?
    var demoProfile = DemoData.profile
    var demoBalance = 30
    var demoPlan: PreviewPlan? = .weekly
    var draftEdits: [String: String] = [:]
    var profile: CandidateProfile { isDemo ? demoProfile : account?.profile ?? CandidateProfile() }
    var balance: Int { isDemo ? demoBalance : account?.balance ?? 0 }
    var tailorCost: Int { isDemo ? 5 : account?.tailorCost ?? 5 }
    private var generation = 0

    func bootstrap() async {
        #if DEBUG
        if Configuration.connectedTest {
            guard let token = ProcessInfo.processInfo.environment["JHM_TEST_TOKEN"], !token.isEmpty else { return }
            await api.connectTestSession(token)
            isSignedIn = true
            await reload()
            return
        }
        if ProcessInfo.processInfo.arguments.contains("--ui-testing") {
            await api.signOut()
            if ProcessInfo.processInfo.arguments.contains("--demo") { demo() }
            return
        }
        #endif
        guard await api.hasSession else { return }
        isSignedIn = true
        await reload()
    }

    func demo() {
        generation += 1
        isDemo = true
        notebook.reset(preview: true)
        isSignedIn = false
        account = nil
        message = nil
        demoProfile = DemoData.profile
        demoBalance = 30
        demoPlan = .weekly
        draftEdits = [:]
        jobs = DemoData.jobs
        drafts = []
        ledger = []
    }

    func reload() async {
        guard !isDemo else { return }
        let current = generation
        isLoading = true
        defer { isLoading = false }
        do {
            async let me = api.get("v1/me", as: Account.self)
            async let list = api.get("v1/jobs", as: [Job].self)
            async let savedDrafts = api.get("v1/drafts", as: [Draft].self)
            async let history = api.get("v1/ledger", as: [LedgerEntry].self)
            let result = try await (me, list, savedDrafts, history)
            guard current == generation else { return }
            (account, jobs, drafts, ledger) = (result.0, result.1, result.2, result.3)
            draftEdits = DraftEditStorage.load(accountID: result.0.id)
            if notebook.accountID != result.0.id { try await notebook.connect(api, account: result.0.id) }
            else { try await notebook.refreshConnection() }
            message = nil
        } catch let error as AppError where error.isUnauthorized {
            guard current == generation else { return }
            await signOut()
            message = error.localizedDescription
        } catch { if current == generation { message = error.localizedDescription } }
    }

    func saveProfile(_ profile: CandidateProfile) async throws {
        if isDemo { demoProfile = profile; return }
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        _ = try await api.raw("v1/profile", method: "PUT", body: encoder.encode(profile))
        await reload()
    }

    // Preview actions never call billing, AI, or the account API.
    func previewApplication(for job: Job) throws -> Draft {
        guard isDemo else { throw WorkspaceError.previewOnly }
        if let existing = drafts.first(where: { $0.jobId == job.id }) { return existing }
        guard !profile.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !profile.experience.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw WorkspaceError.incompleteProfile }
        guard demoBalance >= 5 else { throw WorkspaceError.insufficientCredits }
        let draft = Draft(id: UUID().uuidString, jobId: job.id, text: """
        PROFILE SUMMARY
        \(profile.name) · \(profile.headline)
        \(profile.experience)

        RELEVANT SKILLS
        \(job.skillMatches(profile.skills).joined(separator: " · "))

        COVER LETTER
        Hello \(job.company) team,

        I’m interested in your \(job.title) role. \(profile.experience)

        I’d welcome a conversation about how my experience could support your team. Thank you for considering my application.

        \(profile.name)

        OUTREACH NOTE
        Hello! I’m exploring the \(job.title) opportunity at \(job.company). I’d love to learn more about the team’s priorities and share my relevant work.
        """)
        drafts.insert(draft, at: 0)
        demoBalance -= 5
        ledger.insert(LedgerEntry(id: UUID().uuidString, amount: -5, reason: "Preview application · \(job.company)", createdAt: ISO8601DateFormatter().string(from: Date())), at: 0)
        return draft
    }

    func previewPurchase(_ plan: PreviewPlan) throws {
        guard isDemo else { throw WorkspaceError.previewOnly }
        demoBalance += plan.credits
        if plan != .topUp { demoPlan = plan }
        ledger.insert(LedgerEntry(id: UUID().uuidString, amount: plan.credits, reason: "Demo only · \(plan.title)", createdAt: ISO8601DateFormatter().string(from: Date())), at: 0)
    }

    func text(for draft: Draft) -> String { draftEdits[draft.id] ?? draft.text }

    func saveEdit(_ text: String, for draft: Draft) throws {
        var edits = draftEdits
        edits[draft.id] = text
        if !isDemo, let account { try DraftEditStorage.save(edits, accountID: account.id) }
        draftEdits = edits
    }

    func update(_ job: Job, status: String) async throws {
        if isDemo {
            if let index = jobs.firstIndex(where: { $0.id == job.id }) { jobs[index].status = status }
            return
        }
        let updated = try await api.write("v1/jobs/\(job.id)", method: "PATCH", body: ["status": status], as: Job.self)
        if let index = jobs.firstIndex(where: { $0.id == job.id }) { jobs[index] = updated }
    }

    func signOut() async {
        notebook.reset(preview: false)
        generation += 1
        isDemo = false
        isSignedIn = false
        account = nil
        jobs = []
        drafts = []
        ledger = []
        draftEdits = [:]
        message = nil
        await api.signOut()
    }
}
