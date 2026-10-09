import Foundation

extension NotebookModel {
    func connect(_ client: APIClient, account: String) async throws {
        if accountID != account { reset(preview: false) }
        api = client; accountID = account
        try await refreshConnection(loadProfile: true)
    }

    func refreshConnection(loadProfile: Bool = false) async throws {
        guard let api, let owner = accountID, !isPreview, !isRefreshing else { return }
        isRefreshing = true
        defer { if accountID == owner { isRefreshing = false } }
        async let cap = api.get("v2/capabilities", as: PremiumCapabilities.self)
        async let me = api.get("v1/me", as: Account.self)
        async let feed = api.window("v2/feed", count: max(50, roles.count), as: PremiumJob.self)
        async let activity = api.window("v2/activity", count: max(50, applications.count), as: PremiumApplication.self)
        async let totals = api.get("v2/activity/summary", as: PremiumSummary.self)
        async let auto = api.get("v2/campaigns", as: [PremiumCampaign].self)
        async let products = api.get("v1/products", as: [CatalogProduct].self)
        async let learning = api.get("v2/learning", as: LearningProgress.self)
        let result = try await (cap, me, feed, activity, totals, auto, products, learning)
        guard accountID == owner else { return }
        capabilities = result.0
        remaining = max(0, result.1.balance / max(1, result.0.applicationCreditCost)); allowance = remaining
        roles = result.2.items.map { $0.role() }; nextFeedOffset = result.2.nextOffset
        let mapped = result.3.items.map { item -> ApplicationRecord in
            var record = item.record()
            if let previous = applications.first(where: { $0.id == record.id }) { record.events = previous.events; record.questions = previous.questions }
            return record
        }
        applications = mapped; nextActivityOffset = result.3.nextOffset
        summary = result.4; campaigns = result.5; catalog = result.6
        completedLessons = Set(result.7.completed)
        if loadProfile {
            let envelope = try await api.get("v2/profile", as: PremiumProfile.self)
            guard accountID == owner else { return }
            let details = try envelope.applicationCandidate()
            if let notebook = envelope.profile.notebook { profile = notebook }
            else {
                profile = NotebookProfile(name: envelope.profile.name ?? "", headline: envelope.profile.headline ?? "", portfolio: details.website,
                    location: envelope.profile.location ?? "", targetRoles: envelope.preferences.desiredRoles.joined(separator: ", "))
                profile.sections = ProfileTextParser.parse(details.resumeText.isEmpty ? envelope.profile.experience ?? "" : details.resumeText, filename: "Account profile").sections
                if profile[.skills].isEmpty { profile[.skills] = (envelope.profile.skills ?? []).joined(separator: ", ") }
            }
            candidate = details; preferences = envelope.preferences; revision = envelope.revision
            savedProfile = profile; savedCandidate = candidate; savedPreferences = preferences
        }
        connectionMessage = nil
    }

    func saveConnectedProfile() async throws {
        guard let api, let owner = accountID, !isBusy else { return }
        guard profile.ready else { throw NotebookError.profile }
        isBusy = true; defer { if accountID == owner { isBusy = false } }
        let snapshot = profile
        var details = candidate
        let names = snapshot.name.split(separator: " ", maxSplits: 1).map(String.init)
        details.firstName = names.first ?? ""; details.lastName = names.count > 1 ? names[1] : ""
        details.website = snapshot.portfolio; details.location = snapshot.location
        details.resumeText = NotebookSection.allCases.map { "## \($0.title)\n\(snapshot[$0])" }.joined(separator: "\n\n")
        guard details.resumeText.count <= 19000 else { throw AppError.message("Your profile is too long to save. Keep a shorter career summary here; retain your full source file separately.") }
        guard !details.email.isEmpty, !details.lastName.isEmpty else { throw AppError.message("Add your full name and application email before saving.") }
        var prefs = preferences
        prefs.desiredRoles = snapshot.targetRoles.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        prefs.desiredLocations = snapshot.location.isEmpty ? [] : [snapshot.location]
        let evidence = CandidateProfile(name: snapshot.name, headline: snapshot.headline, location: snapshot.location, skills: snapshot.skills,
            experience: details.resumeText, aiConsent: details.tailoringConsent)
        var body: [String: Any] = ["profile": try apiDictionary(evidence), "candidate": try apiDictionary(details), "preferences": try apiDictionary(prefs), "notebook": try apiDictionary(snapshot)]
        body["expected_revision"] = revision.map { $0 as Any } ?? NSNull()
        let result = try await api.write("v2/profile", method: "PUT", body: body, as: ProfileSaveResult.self)
        guard accountID == owner else { return }
        revision = result.revision; savedProfile = snapshot
        candidate = details; savedCandidate = details; preferences = prefs; savedPreferences = prefs
        roles = []; connectionMessage = "Profile saved. Job matches are being refreshed."
    }

    func submitConnected(_ role: SuggestedRole) async throws -> ApplicationRecord {
        guard let api, let owner = accountID else { throw NotebookError.backend }
        if let existing = applications.first(where: { $0.role.id == role.id }) { return existing }
        guard !profileDirty else { throw AppError.message("Save your profile changes before applying.") }
        guard candidate.submissionConsent else { throw AppError.message("Authorize applications in your profile first.") }
        guard !loadingApplicationIDs.contains(role.id) else { throw AppError.message("This application is already being queued.") }
        loadingApplicationIDs.insert(role.id); defer { loadingApplicationIDs.remove(role.id) }
        // Retain the same key across retries/relaunches. No profile content is stored here.
        let storageKey = "application-request.\(owner).\(role.id)"
        let key = UserDefaults.standard.string(forKey: storageKey).flatMap(UUID.init(uuidString:)) ?? UUID()
        UserDefaults.standard.set(key.uuidString, forKey: storageKey)
        let ack = try await api.write("v2/listings/\(role.id)/apply", method: "POST", body: ["authorize_submission": true, "answers": [:]], as: ApplicationAcknowledgement.self, key: key)
        guard accountID == owner else { throw CancellationError() }
        var record = ApplicationRecord(id: ack.id, role: role, stage: .server(state: ack.state, outcome: nil), date: Date(timeIntervalSince1970: ack.createdAt), automatic: false, events: [])
        record.serverState = ack.state
        applications.insert(record, at: 0)
        do { try await refreshConnection() } catch { connectionMessage = "Application queued. Balance or history refresh failed; pull to refresh. Do not apply again." }
        return applications.first { $0.id == ack.id } ?? record
    }

    func refreshApplication(_ id: String) async throws {
        guard let api, let owner = accountID else { return }
        let detail = try await api.get("v2/applications/\(id)", as: PremiumApplication.self)
        guard accountID == owner else { return }
        let record = detail.record()
        if let index = applications.firstIndex(where: { $0.id == id }) { applications[index] = record }
        else { applications.insert(record, at: 0) }
    }

    func loadMoreActivity() async throws {
        guard let api, let offset = nextActivityOffset, let owner = accountID else { return }
        let page = try await api.get("v2/activity?limit=50&offset=\(offset)", as: PremiumPage<PremiumApplication>.self)
        guard accountID == owner else { return }
        for item in page.items where !applications.contains(where: { $0.id == item.id }) { applications.append(item.record()) }
        nextActivityOffset = page.nextOffset
    }

    func loadMoreRoles() async throws {
        guard let api, let offset = nextFeedOffset, let owner = accountID else { return }
        let page = try await api.get("v2/feed?limit=50&offset=\(offset)", as: PremiumPage<PremiumJob>.self)
        guard accountID == owner else { return }
        for item in page.items where !roles.contains(where: { $0.id == item.id }) { roles.append(item.role()) }
        nextFeedOffset = page.nextOffset
    }

    func setOutcome(_ id: String, status: String) async throws {
        guard let api else { return }
        _ = try await api.write("v2/applications/\(id)/outcome", method: "PUT", body: ["status": status, "note": "Updated by the account owner"], as: JSONValue.self)
        try await refreshApplication(id)
    }

    func retryApplication(_ record: ApplicationRecord, answers: [String: String]) async throws {
        guard let api else { return }
        _ = try await api.write("v2/applications/\(record.id)/answers", method: "PUT", body: ["authorize_submission": true, "answers": answers, "expected_generation": record.generation], as: JSONValue.self)
        try await refreshApplication(record.id)
    }

    func cancelApplication(_ id: String) async throws {
        guard let api else { return }
        _ = try await api.raw("v2/applications/\(id)/cancel", method: "POST")
        try await refreshApplication(id)
        try await refreshConnection()
    }

    func startCampaign(maximum: Int, daily: Int, threshold: Int) async throws {
        guard let api else { return }
        guard !profileDirty else { throw AppError.message("Save your profile and preferences first.") }
        _ = try await api.write("v2/campaigns", method: "POST", body: ["maximum": maximum, "daily_limit": daily, "threshold": Double(threshold) / 100, "duration_days": 30, "authorize_submission": true], as: JSONValue.self)
        try await refreshConnection()
    }
    func pauseCampaign(_ id: String) async throws {
        guard let api else { return }
        _ = try await api.raw("v2/campaigns/\(id)/pause", method: "POST")
        try await refreshConnection()
    }
    func toggleLesson(_ skill: String) async throws {
        guard let api, let owner = accountID, !isBusy else { return }
        isBusy = true; defer { if accountID == owner { isBusy = false } }
        var next = completedLessons
        if next.contains(skill) { next.remove(skill) } else { next.insert(skill) }
        let result = try await api.write("v2/learning", method: "PUT", body: ["completed": next.sorted()], as: LearningProgress.self)
        guard accountID == owner else { return }
        completedLessons = Set(result.completed)
    }
}

extension APIClient {
    func window<T: Decodable>(_ path: String, count: Int, as: T.Type) async throws -> PremiumPage<T> {
        var result = try await get("\(path)?limit=50", as: PremiumPage<T>.self)
        while result.items.count < count, let offset = result.nextOffset {
            let page = try await get("\(path)?limit=50&offset=\(offset)", as: PremiumPage<T>.self)
            result.items.append(contentsOf: page.items); result.nextOffset = page.nextOffset
        }
        return result
    }
}
