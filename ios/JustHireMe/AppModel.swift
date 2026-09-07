import Foundation
import Observation

@MainActor @Observable
final class AppModel {
    let api = APIClient()
    var isDemo = false
    var isSignedIn = false
    var isLoading = false
    var account: Account?
    var jobs: [Job] = []
    var drafts: [Draft] = []
    var ledger: [LedgerEntry] = []
    var message: String?
    var profile: CandidateProfile { isDemo ? DemoData.profile : account?.profile ?? CandidateProfile() }
    private var generation = 0

    func bootstrap() async {
        #if DEBUG
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
        } catch { if current == generation { message = error.localizedDescription } }
    }

    func saveProfile(_ profile: CandidateProfile) async throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        _ = try await api.raw("v1/profile", method: "PUT", body: encoder.encode(profile))
        await reload()
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
        generation += 1
        isDemo = false
        isSignedIn = false
        account = nil
        jobs = []
        drafts = []
        ledger = []
        await api.signOut()
    }
}
