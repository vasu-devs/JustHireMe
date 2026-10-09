import Foundation

enum Configuration {
    static var connectedTest: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--connected-testing")
        #else
        return false
        #endif
    }
    static var apiURL: URL {
        get throws {
            #if DEBUG
            if connectedTest { return URL(string: "http://127.0.0.1:8769")! }
            #endif
            return try url("APIBaseURL")
        }
    }
    // Copy Configuration.example.plist to Configuration.plist before a real build.
    // Public Supabase key only. Never put service-role or AI keys in the app.
    static var values: [String: String] {
        guard let url = Bundle.main.url(forResource: "Configuration", withExtension: "plist"),
              let data = try? Data(contentsOf: url),
              let values = try? PropertyListDecoder().decode([String: String].self, from: data) else { return [:] }
        return values
    }
    static func url(_ key: String) throws -> URL {
        guard let raw = values[key], let url = URL(string: raw), url.scheme == "https",
              url.host != nil, !raw.contains("REPLACE") else {
            throw AppError.message("This build is not connected yet. You can explore the demo while setup is completed.")
        }
        return url
    }
    static var publicKey: String { values["SupabasePublicKey"] ?? "" }
}

enum AppError: LocalizedError, Equatable {
    case message(String)
    case http(Int, String)
    case unauthorized
    var errorDescription: String? {
        switch self {
        case .message(let text): return text
        case .http(_, let text): return text
        case .unauthorized: return "Your session has expired. Please sign in again."
        }
    }
    var status: Int? { if case .http(let code, _) = self { return code }; return nil }
    var isUnauthorized: Bool { self == .unauthorized }
}
