import CryptoKit
import Foundation

// Device-local edits are scoped to the authenticated account. Demo edits stay in memory.
enum DraftEditStorage {
    private static func url(accountID: String) throws -> URL {
        let directory = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                    appropriateFor: nil, create: true).appendingPathComponent("DraftEdits", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var excluded = directory
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try excluded.setResourceValues(values)
        let key = SHA256.hash(data: Data(accountID.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(key + ".json")
    }
    static func load(accountID: String) -> [String: String] {
        guard let location = try? url(accountID: accountID), let data = try? Data(contentsOf: location),
              let edits = try? JSONDecoder().decode([String: String].self, from: data) else { return [:] }
        return edits
    }
    static func save(_ edits: [String: String], accountID: String) throws {
        try JSONEncoder().encode(edits).write(to: url(accountID: accountID), options: [.atomic, .completeFileProtection])
    }
    static func remove(accountID: String) throws {
        let location = try url(accountID: accountID)
        if FileManager.default.fileExists(atPath: location.path) { try FileManager.default.removeItem(at: location) }
    }
}
