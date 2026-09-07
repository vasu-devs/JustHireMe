import Foundation

enum Configuration {
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

enum AppError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text) = self { return text }; return nil }
}
