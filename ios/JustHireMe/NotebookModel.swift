import Foundation
import Observation

enum NotebookSection: String, CaseIterable, Identifiable, Codable {
    case about, experience, education, projects, skills, achievements
    var id: String { rawValue }
    var title: String { rawValue.capitalized }
    var symbol: String {
        switch self { case .about: "person.text.rectangle"; case .experience: "briefcase"; case .education: "graduationcap"; case .projects: "square.stack.3d.up"; case .skills: "pencil.tip"; case .achievements: "rosette" }
    }
}

struct NotebookProfile: Codable, Equatable {
    var name = ""
    var headline = ""
    var portfolio = ""
    var location = "Remote"
    var targetRoles = ""
    var sections: [String: String] = [:]
    subscript(_ section: NotebookSection) -> String {
        get { sections[section.rawValue] ?? "" }
        set { sections[section.rawValue] = newValue }
    }
    var skills: [String] { self[.skills].components(separatedBy: CharacterSet(charactersIn: ",\n•;")).map { $0.trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "-*•"))) }.filter { !$0.isEmpty } }
    var completedSections: Int { NotebookSection.allCases.filter { !self[$0].trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.count }
    var ready: Bool { !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && completedSections > 0 }
}

struct ProfileImport: Identifiable {
    let id = UUID()
    var filename: String
    var sections: [String: String]
    var pending = false
    var payload: Data? = nil
    var summary: String { pending ? "Added for processing" : "\(sections.count) sections found · review before adding" }
}

enum ProfileTextParser {
    // Deterministic, local section recognition. Uploaded instructions are never executed.
    static func parse(_ text: String, filename: String) -> ProfileImport {
        var result: [String: [String]] = [:]
        var current = NotebookSection.about
        for raw in text.components(separatedBy: .newlines) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            let heading = line.trimmingCharacters(in: CharacterSet(charactersIn: "#*: _")).lowercased()
            let aliases: [String: NotebookSection] = ["about": .about, "summary": .about, "profile": .about,
                "experience": .experience, "work experience": .experience, "employment": .experience,
                "education": .education, "projects": .projects, "selected projects": .projects,
                "skills": .skills, "technical skills": .skills, "achievements": .achievements, "certifications": .achievements]
            if let section = aliases[heading] { current = section; continue }
            if !line.isEmpty { result[current.rawValue, default: []].append(line) }
        }
        return ProfileImport(filename: filename, sections: result.mapValues { $0.joined(separator: "\n") })
    }
}

struct SuggestedRole: Identifiable, Hashable {
    let id: String
    let title: String
    let company: String
    let location: String
    let type: String
    let salary: String
    let description: String
    let requirements: [String]
    var relevance: Double? = nil
    var canApply = true
    var url = ""
    var lastChecked: Date? = nil
    func matched(_ profile: NotebookProfile) -> [String] {
        requirements.filter { skill in profile.skills.contains { $0.localizedCaseInsensitiveCompare(skill) == .orderedSame } }
    }
    func score(_ profile: NotebookProfile) -> Int {
        if let relevance { return Int((relevance * 100).rounded()) }
        return requirements.isEmpty ? 0 : Int((Double(matched(profile).count) / Double(requirements.count) * 100).rounded())
    }
}

enum ApplicationStage: String, CaseIterable, Identifiable, Codable {
    case submitted, interviewing, offer, rejected, needsAttention, queued, preparing, submitting, failed, cancelled, uncertain, withdrawn
    var id: String { rawValue }
    var title: String { self == .needsAttention ? "Needs attention" : rawValue.capitalized }
    var symbol: String { switch self { case .submitted: "paperplane"; case .interviewing: "bubble.left.and.bubble.right"; case .offer: "star"; case .rejected: "arrow.uturn.left"; case .needsAttention, .failed, .uncertain: "exclamationmark.circle"; case .queued, .preparing, .submitting: "clock"; case .cancelled, .withdrawn: "xmark.circle" } }
    static func server(state: String, outcome: String?) -> Self {
        if state == "submitted" {
            switch outcome { case "interview": return .interviewing; case "offer": return .offer; case "rejected": return .rejected; case "withdrawn": return .withdrawn; default: return .submitted }
        }
        if state == "needs_user" { return .needsAttention }
        return Self(rawValue: state) ?? .uncertain
    }
}

struct ApplicationRecord: Identifiable {
    let id: String
    let role: SuggestedRole
    var stage: ApplicationStage
    let date: Date
    let automatic: Bool
    var events: [String]
    var serverState = ""
    var reason = ""
    var outcomeSource: String? = nil
    var outcomeNote = ""
    var resumeAvailable = false
    var emailStatus = "not_requested"
    var generation = 0
    var questions: [RequiredAnswer] = []
}

enum ApplicationPlan: String, CaseIterable, Identifiable {
    case single, weekly, monthly
    var id: String { rawValue }
    var name: String { switch self { case .single: "Single application"; case .weekly: "Weekly"; case .monthly: "Monthly" } }
    var count: Int { switch self { case .single: 1; case .weekly: 10; case .monthly: 40 } }
    var cadence: String { switch self { case .single: "one time"; case .weekly: "per week"; case .monthly: "per month" } }
}

enum NotebookError: LocalizedError {
    case backend, profile, allowance, empty
    var errorDescription: String? {
        switch self {
        case .backend: "This service is not connected yet. Explore the preview to try the full flow."
        case .profile: "Add your name and at least one profile section before applying."
        case .allowance: "You’ve used your application allowance. Choose a plan to continue."
        case .empty: "There’s no readable text here. Try a text-based PDF, Markdown, or pasted notes."
        }
    }
}

@MainActor @Observable
final class NotebookModel {
    var isPreview = false
    var profile = NotebookProfile()
    var sources: [ProfileImport] = []
    var roles: [SuggestedRole] = []
    var applications: [ApplicationRecord] = []
    var activePlan: ApplicationPlan = .weekly
    var allowance = 0
    var remaining = 0
    var autoEnabled = false
    var autoMinimum = 75
    var autoDailyLimit = 2
    var completedLessons: Set<String> = []
    var api: APIClient?
    var accountID: String?
    var capabilities: PremiumCapabilities?
    var candidate = ApplicationCandidate()
    var preferences = MatchPreferences()
    var revision: String?
    var savedProfile = NotebookProfile()
    var savedCandidate = ApplicationCandidate()
    var savedPreferences = MatchPreferences()
    var campaigns: [PremiumCampaign] = []
    var catalog: [CatalogProduct] = []
    var summary: PremiumSummary?
    var nextActivityOffset: Int?
    var nextFeedOffset: Int?
    var connectionMessage: String?
    var isBusy = false
    var isRefreshing = false
    var loadingApplicationIDs: Set<String> = []
    var isConnected: Bool { api != nil && accountID != nil && !isPreview }
    var profileDirty: Bool { profile != savedProfile || candidate != savedCandidate || preferences != savedPreferences }

    func reset(preview: Bool) {
        api = nil; accountID = nil; capabilities = nil; revision = nil
        candidate = ApplicationCandidate(); preferences = MatchPreferences()
        savedProfile = NotebookProfile(); savedCandidate = ApplicationCandidate(); savedPreferences = MatchPreferences()
        campaigns = []; catalog = []; summary = nil; connectionMessage = nil
        nextActivityOffset = nil; nextFeedOffset = nil; isBusy = false; isRefreshing = false; loadingApplicationIDs = []
        isPreview = preview
        profile = preview ? NotebookSamples.profile : NotebookProfile()
        sources = preview ? [ProfileImport(filename: "portfolio.md", sections: NotebookSamples.profile.sections)] : []
        roles = preview ? NotebookSamples.roles : []
        applications = preview ? NotebookSamples.applications : []
        allowance = preview ? 10 : 0; remaining = preview ? 7 : 0
        activePlan = .weekly; autoEnabled = false; autoMinimum = 75; autoDailyLimit = 2
        completedLessons = []
    }

    func add(_ proposal: ProfileImport) throws {
        guard proposal.pending || !proposal.sections.isEmpty else { throw NotebookError.empty }
        for section in NotebookSection.allCases {
            guard let addition = proposal.sections[section.rawValue], !addition.isEmpty else { continue }
            let existing = profile[section]
            // Preserve previous entries and manual edits; imports are additive.
            if !existing.contains(addition) { profile[section] = existing.isEmpty ? addition : existing + "\n\n" + addition }
        }
        sources.insert(proposal, at: 0)
    }

    @discardableResult func apply(_ role: SuggestedRole, automatic: Bool = false) throws -> ApplicationRecord {
        guard isPreview else { throw NotebookError.backend }
        if let existing = applications.first(where: { $0.role.id == role.id }) { return existing }
        guard profile.ready else { throw NotebookError.profile }
        guard remaining > 0 else { throw NotebookError.allowance }
        let record = ApplicationRecord(id: UUID().uuidString, role: role, stage: .submitted, date: Date(), automatic: automatic,
            events: ["Profile checked", "Application prepared", "Submission simulated · no employer contacted"])
        applications.insert(record, at: 0)
        remaining -= 1
        return record
    }

    func eligibleForAuto(_ role: SuggestedRole) -> Bool {
        let titles = profile.targetRoles.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        let locationMatches = profile.location.isEmpty || role.location.localizedCaseInsensitiveContains(profile.location)
        return locationMatches && titles.contains { role.title.localizedCaseInsensitiveContains($0) } && role.score(profile) >= autoMinimum
            && !applications.contains { $0.role.id == role.id }
    }
    func runAutomationPreview() throws -> Int {
        guard isPreview else { throw NotebookError.backend }
        guard autoEnabled else { return 0 }
        let today = applications.filter { $0.automatic && Calendar.current.isDateInToday($0.date) }.count
        let limit = min(max(0, autoDailyLimit - today), remaining)
        let candidates = Array(roles.filter(eligibleForAuto).prefix(limit))
        for role in candidates { try apply(role, automatic: true) }
        return candidates.count
    }
    func choose(_ plan: ApplicationPlan) throws {
        guard isPreview else { throw NotebookError.backend }
        if plan == .single { remaining += 1; allowance += 1 }
        else { activePlan = plan; allowance = plan.count; remaining = plan.count }
    }
    func update(_ record: ApplicationRecord, stage: ApplicationStage) {
        guard isPreview, let index = applications.firstIndex(where: { $0.id == record.id }) else { return }
        applications[index].stage = stage
        applications[index].events.append("Preview outcome updated to \(stage.title.lowercased())")
    }
    var gaps: [String] {
        let missing = roles.flatMap { role in role.requirements.filter { !role.matched(profile).contains($0) } }
        return Set(missing).sorted { left, right in
            let a = missing.filter { $0 == left }.count, b = missing.filter { $0 == right }.count
            return a == b ? left < right : a > b
        }
    }
}

enum NotebookSamples {
    static let profile: NotebookProfile = {
        var p = NotebookProfile(name: "Alex Morgan", headline: "Product designer", portfolio: "https://alex.example.com", location: "Remote")
        p.targetRoles = "Product Designer, UX Designer"
        p[.about] = "Product designer with four years of experience in research, onboarding and accessible interfaces. Looking for a remote product design role."
        p[.experience] = "Product Designer · Studio Fern\n2022 — Present\nDesigned onboarding and collaborated with engineering from research to release."
        p[.education] = "B.Des, Communication Design\n2018 — 2022"
        p[.projects] = "Little Notes\nAn accessible journaling concept. Research, wireframes, and interactive Figma prototypes."
        p[.skills] = "Figma, Research, Prototyping, Accessibility"
        p[.achievements] = "Community design mentor\nLed peer portfolio reviews for early-career designers."
        return p
    }()
    static let roles = [
        SuggestedRole(id: "match-1", title: "Product Designer", company: "Northstar", location: "Remote", type: "Full time", salary: "$90k–120k · sample", description: "Make everyday work feel lighter. Join a small product team, lead discovery, and carry ideas from a first sketch to a considered release.", requirements: ["Figma", "Research", "Prototyping", "Design systems"]),
        SuggestedRole(id: "match-2", title: "UX Designer", company: "Moss", location: "Remote", type: "Full time", salary: "$85k–110k · sample", description: "Design thoughtful tools for creative people. Make complex workflows accessible, approachable, and a little more human.", requirements: ["Figma", "Research", "Accessibility", "Prototyping"]),
        SuggestedRole(id: "match-3", title: "Design Engineer", company: "Paperplane", location: "Bengaluru", type: "Hybrid", salary: "₹22–32L · sample", description: "Bridge design and development. Build expressive interfaces and help the team turn its component library into a shared design language.", requirements: ["Figma", "Prototyping", "JavaScript", "Design systems"])
    ]
    static let applications: [ApplicationRecord] = [
        history("history-1", "UX Designer", "Forma", .interviewing, 2),
        history("history-2", "Product Designer", "Linen", .submitted, 3),
        history("history-3", "Visual Designer", "Sunday", .offer, 8),
        history("history-4", "Product Designer", "Orbit", .rejected, 12)
    ]
    private static func history(_ id: String, _ title: String, _ company: String, _ stage: ApplicationStage, _ days: Int) -> ApplicationRecord {
        ApplicationRecord(id: id, role: SuggestedRole(id: id, title: title, company: company, location: "Remote", type: "Full time", salary: "", description: "Sample application history", requirements: ["Figma", "Research"]), stage: stage, date: Date().addingTimeInterval(Double(-days) * 86400), automatic: false, events: ["Application submitted · sample", "\(stage.title) · sample outcome"])
    }
    static let importText = "# About\nI design thoughtful products.\n# Skills\nFigma, Research, Accessibility\n# Projects\nAn accessible reading app.\n# Education\nB.Des, Communication Design\n# Experience\nDesigner at Studio Fern, 2022–present."
}
