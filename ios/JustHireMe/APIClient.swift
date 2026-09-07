import Foundation

struct AuthSession: Codable {
    let accessToken: String
    let refreshToken: String
    let expiresAt: Double
}

actor APIClient {
    private var session: AuthSession?
    private var refreshTask: Task<AuthSession, Error>?
    private var epoch = 0
    private let transport: URLSession
    private let decoder: JSONDecoder

    init() {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 120
        config.urlCache = nil
        transport = URLSession(configuration: config)
        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        if let data = Keychain.load() { session = try? JSONDecoder().decode(AuthSession.self, from: data) }
    }

    var hasSession: Bool { session != nil }

    func requestCode(email: String) async throws {
        _ = try await auth("otp", body: ["email": email, "create_user": true])
    }

    func verify(email: String, code: String) async throws {
        let data = try await auth("verify", body: ["email": email, "token": code, "type": "email"])
        let value = try decoder.decode(AuthSession.self, from: data)
        try Keychain.save(JSONEncoder().encode(value))
        session = value
    }

    func signOut() async {
        epoch += 1
        let token = session?.accessToken
        refreshTask?.cancel()
        refreshTask = nil
        session = nil
        Keychain.clear()
        if let token { _ = try? await auth("logout", body: [:], bearer: token) }
    }

    private func auth(_ path: String, body: [String: Any], bearer: String? = nil) async throws -> Data {
        let base = try Configuration.url("SupabaseURL")
        let url: URL
        if path == "token" {
            var parts = URLComponents(url: base.appendingPathComponent("auth/v1/token"), resolvingAgainstBaseURL: false)!
            parts.queryItems = [URLQueryItem(name: "grant_type", value: "refresh_token")]
            url = parts.url!
        } else { url = base.appendingPathComponent("auth/v1/" + path) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(Configuration.publicKey, forHTTPHeaderField: "apikey")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let bearer { request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization") }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await send(request)
    }

    private func token() async throws -> String {
        guard let current = session else { throw AppError.message("Please sign in again.") }
        if current.expiresAt > Date().timeIntervalSince1970 + 60 { return current.accessToken }
        if let refreshTask { return try await refreshTask.value.accessToken }
        let currentEpoch = epoch
        let task = Task { () async throws -> AuthSession in
            let data = try await auth("token", body: ["refresh_token": current.refreshToken])
            return try decoder.decode(AuthSession.self, from: data)
        }
        refreshTask = task
        defer { refreshTask = nil }
        let refreshed = try await task.value
        guard epoch == currentEpoch else { throw CancellationError() }
        try Keychain.save(JSONEncoder().encode(refreshed))
        session = refreshed
        return refreshed.accessToken
    }

    func raw(_ path: String, method: String = "GET", body: Data? = nil, key: UUID? = nil) async throws -> Data {
        var request = URLRequest(url: try Configuration.url("APIBaseURL").appendingPathComponent(path))
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(try await token())", forHTTPHeaderField: "Authorization")
        if let key { request.setValue(key.uuidString, forHTTPHeaderField: "Idempotency-Key") }
        return try await send(request)
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        try decoder.decode(type, from: await raw(path))
    }

    func write<T: Decodable>(_ path: String, method: String, body: [String: Any], as type: T.Type,
                             key: UUID? = nil) async throws -> T {
        let bytes = try JSONSerialization.data(withJSONObject: body)
        return try decoder.decode(type, from: await raw(path, method: method, body: bytes, key: key))
    }

    private func send(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await transport.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw AppError.message("No response. Please retry.") }
        guard (200...299).contains(response.statusCode) else {
            let payload = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let detail = payload?["detail"] as? String ?? payload?["msg"] as? String
            throw AppError.message(detail ?? "The request could not be completed (\(response.statusCode)). Please retry.")
        }
        return data
    }
}
