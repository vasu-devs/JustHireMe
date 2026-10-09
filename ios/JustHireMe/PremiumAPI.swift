import Foundation

struct PremiumCapabilities: Decodable {
    var matchingAvailable: Bool
    var submissionAvailable: Bool
    var applicationCreditCost: Int
    var resumeTailoringAvailable: Bool
    var emailNotificationsAvailable: Bool
}

struct ApplicationCandidate: Codable, Equatable {
    var firstName = ""
    var lastName = ""
    var email = ""
    var phone = ""
    var resumeText = ""
    var submissionConsent = false
    var tailoringConsent = false
    var emailNotifications = false
    var location = ""
    var linkedin = ""
    var website = ""
    var savedAnswers: [String: String] = [:]
}

struct MatchPreferences: Codable, Equatable {
    var matchingConsent = false
    var enabled = false
    var threshold = 0.8
    var desiredRoles: [String] = []
    var desiredLocations: [String] = []
    var constraints = ""
    var discoveryConsent = false
}

struct PremiumProfile: Decodable {
    struct Evidence: Decodable {
        var name: String?
        var headline: String?
        var location: String?
        var skills: [String]?
        var experience: String?
        var notebook: NotebookProfile?
    }
    var profile: Evidence
    var candidate: [String: JSONValue]
    var preferences: MatchPreferences
    var revision: String?
    func applicationCandidate() throws -> ApplicationCandidate {
        guard !candidate.isEmpty else { return ApplicationCandidate() }
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(ApplicationCandidate.self, from: JSONEncoder().encode(candidate))
    }
}

struct ProfileSaveResult: Decodable { var revision: String }
struct LearningProgress: Codable { var completed: [String] }
struct PremiumPage<Item: Decodable>: Decodable { var items: [Item]; var nextOffset: Int? }

struct PremiumJob: Decodable {
    var id: String
    var title: String
    var company: String
    var location: String
    var description: String
    var url: String
    var relevanceProbability: Double?
    var canAutoApply: Bool?
    var lastSeen: Double?

    func role() -> SuggestedRole {
        let vocabulary = ["Python", "TypeScript", "JavaScript", "React", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "Swift", "Figma", "Accessibility", "Design systems", "Research", "Prototyping", "RAG", "GraphQL", "SQL"]
        let evidence = Job(id: id, title: title, company: company, location: location, url: url, description: description, status: "")
        var value = SuggestedRole(id: id, title: title, company: company, location: location, type: "", salary: "", description: description, requirements: evidence.skillMatches(vocabulary))
        value.relevance = relevanceProbability
        value.canApply = canAutoApply ?? false
        value.url = url
        value.lastChecked = lastSeen.map(Date.init(timeIntervalSince1970:))
        return value
    }
}

struct PremiumTimelineEvent: Decodable {
    var kind: String
    var detail: [String: JSONValue]
    var createdAt: Double
}

struct ApplicationAcknowledgement: Decodable { var id: String; var state: String; var createdAt: Double }

struct PremiumApplication: Decodable {
    var id: String
    var job: PremiumJob
    var state: String
    var reason: String
    var createdAt: Double
    var campaignId: String?
    var employerStatus: String?
    var statusSource: String?
    var statusNote: String?
    var emailStatus: String
    var resumeAvailable: Bool
    var generation: Int
    var timeline: [PremiumTimelineEvent]?

    func record() -> ApplicationRecord {
        let stage = ApplicationStage.server(state: state, outcome: employerStatus)
        var value = ApplicationRecord(id: id, role: job.role(), stage: stage, date: Date(timeIntervalSince1970: createdAt), automatic: campaignId != nil,
            events: (timeline ?? []).map { event in
                let stamp = Date(timeIntervalSince1970: event.createdAt).formatted(date: .abbreviated, time: .shortened)
                let label = event.kind.replacingOccurrences(of: "_", with: " ").capitalized
                return "\(stamp) · \(label)"
            })
        value.serverState = state; value.reason = reason; value.outcomeSource = statusSource
        value.outcomeNote = statusNote ?? ""; value.resumeAvailable = resumeAvailable
        value.emailStatus = emailStatus; value.generation = generation
        value.questions = (timeline ?? []).flatMap { $0.detail["questions"]?.array ?? [] }.compactMap(RequiredAnswer.init)
        return value
    }
}

struct PremiumSummary: Decodable { var total: Int; var applications: [String: Int]; var employerOutcomes: [String: Int] }
struct PremiumCampaign: Decodable, Identifiable {
    var id: String; var status: String; var maximum: Int; var dailyLimit: Int; var threshold: Double; var reserved: Int; var expiresAt: Double
}

struct RequiredAnswer: Identifiable {
    var id: String { label }
    var label: String
    var options: [String]
    var supported: Bool
    var required: Bool
    init?(_ value: JSONValue) {
        guard let object = value.object, let label = object["label"]?.string, !label.isEmpty else { return nil }
        self.label = label
        var type = object["type"]?.string ?? ""
        var rawOptions = object["options"]?.array ?? []
        // Greenhouse Job Board API questions carry their control inside `fields`.
        if let field = object["fields"]?.array?.first?.object {
            type = field["type"]?.string ?? type
            if rawOptions.isEmpty { rawOptions = field["values"]?.array ?? [] }
        }
        var choices = rawOptions.compactMap { $0.string ?? $0.object?["label"]?.string }
        if type == "checkbox" && choices.isEmpty { choices = ["Yes", "No"] }
        options = choices
        required = object["required"]?.bool ?? true
        let free = ["text", "textarea", "email", "tel", "url", "number", "select", "input_text"]
        supported = free.contains(type) || (["radio", "checkbox", "multi_value_single_select"].contains(type) && !choices.isEmpty)
    }
}

enum JSONValue: Codable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let value = try? c.decode(Bool.self) { self = .bool(value) }
        else if let value = try? c.decode(String.self) { self = .string(value) }
        else if let value = try? c.decode(Double.self) { self = .number(value) }
        else if let value = try? c.decode([String: JSONValue].self) { self = .object(value) }
        else { self = .array(try c.decode([JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self { case .string(let v): try c.encode(v); case .number(let v): try c.encode(v); case .bool(let v): try c.encode(v); case .object(let v): try c.encode(v); case .array(let v): try c.encode(v); case .null: try c.encodeNil() }
    }
    var string: String? { if case .string(let v) = self { return v }; return nil }
    var bool: Bool? { if case .bool(let v) = self { return v }; return nil }
    var array: [JSONValue]? { if case .array(let v) = self { return v }; return nil }
    var object: [String: JSONValue]? { if case .object(let v) = self { return v }; return nil }
}

func apiDictionary<T: Encodable>(_ value: T) throws -> [String: Any] {
    let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
    return try JSONSerialization.jsonObject(with: encoder.encode(value)) as! [String: Any]
}
