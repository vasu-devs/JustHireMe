import Foundation

struct CandidateProfile: Codable, Equatable {
    var name = ""
    var headline = ""
    var location = ""
    var skills: [String] = []
    var experience = ""
    var aiConsent = false
}

struct Account: Decodable {
    let id: String
    let purchaseToken: UUID
    var balance: Int
    var profile: CandidateProfile
    let activeSubscriptions: [String]
    let billingAvailable: Bool
    let tailoringAvailable: Bool
    let tailorCost: Int
}

struct Job: Codable, Identifiable, Hashable {
    let id: String
    var title: String
    var company: String
    var location: String
    var url: String
    var description: String
    var status: String

    func skillMatches(_ skills: [String]) -> [String] {
        skills.filter { skill in
            let escaped = NSRegularExpression.escapedPattern(for: skill)
            return description.range(of: "(?<![\\p{L}\\p{N}])" + escaped + "(?![\\p{L}\\p{N}])",
                                     options: [.regularExpression, .caseInsensitive]) != nil
        }
    }
}

struct Draft: Decodable, Identifiable {
    let id: String
    let jobId: String
    let text: String
}

enum PreviewPlan: String, CaseIterable, Identifiable {
    case weekly, monthly, topUp
    var id: String { rawValue }
    var title: String { switch self { case .weekly: "Focus week"; case .monthly: "Monthly momentum"; case .topUp: "A little extra" } }
    var credits: Int { switch self { case .weekly: 30; case .monthly: 150; case .topUp: 50 } }
    var detail: String { switch self { case .weekly: "30 credits every week"; case .monthly: "150 credits every month"; case .topUp: "50 credits, one time" } }
    var note: String { self == .topUp ? "No subscription" : "Renews automatically. Cancel anytime." }
}

enum WorkspaceError: LocalizedError {
    case previewOnly, insufficientCredits, incompleteProfile
    var errorDescription: String? {
        switch self {
        case .previewOnly: "This action is only available in the preview."
        case .insufficientCredits: "You need 5 demo credits. Choose a plan to continue."
        case .incompleteProfile: "Add your name and experience in your profile first."
        }
    }
}

struct LedgerEntry: Decodable, Identifiable {
    let id: String
    let amount: Int
    let reason: String
    let createdAt: String
}

struct CatalogProduct: Decodable, Identifiable {
    let id: String
    let credits: Int
    let kind: String
    let period: String?
}

enum DemoData {
    static let profile = CandidateProfile(name: "Alex Morgan", headline: "Product designer", location: "Remote",
        skills: ["Figma", "Research", "Prototyping", "Accessibility"],
        experience: "Product designer with experience simplifying onboarding and designing accessible tools.")
    static let jobs = [
        Job(id: "demo-1", title: "Product Designer", company: "Northstar", location: "Remote · Full time", url: "",
            description: "Help a small team make work feel simpler. Lead research, explore ideas in Figma, and bring thoughtful prototyping and accessibility practices to our product. Partner with engineering from first sketch to release.", status: "saved"),
        Job(id: "demo-2", title: "Senior UX Designer", company: "Forma", location: "Bengaluru · Hybrid", url: "",
            description: "Shape useful tools for growing businesses. Bring research, interaction design, and clear communication to a collaborative team. Experience building and maintaining design systems in Figma is valuable.", status: "interviewing"),
        Job(id: "demo-3", title: "Design Engineer", company: "Fieldwork", location: "Remote · Contract", url: "",
            description: "Bridge design and engineering to ship expressive, accessible experiences. Work across prototyping, React, and motion design. Own a feature from concept to production with a small, thoughtful team.", status: "applied")
    ]
}
