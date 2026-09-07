import XCTest
@testable import JustHireMe

final class ModelsTests: XCTestCase {
    @MainActor
    func testDemoUsesSampleDataWithoutCreatingACloudAccount() {
        let model = AppModel()
        model.demo()
        XCTAssertTrue(model.isDemo)
        XCTAssertFalse(model.isSignedIn)
        XCTAssertNil(model.account)
        XCTAssertEqual(model.jobs.count, 3)
        XCTAssertEqual(model.profile.name, "Alex Morgan")
        XCTAssertTrue(model.drafts.isEmpty)
    }

    func testProfileEncodingMatchesCloudContract() throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        var profile = CandidateProfile()
        profile.aiConsent = true
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(profile)) as? [String: Any])
        XCTAssertEqual(object["ai_consent"] as? Bool, true)
        XCTAssertNil(object["aiConsent"])
    }

    func testAuthResponseDecodesSessionExpiry() throws {
        let data = Data(#"{"access_token":"test-only","refresh_token":"test-refresh","expires_at":1790000000}"#.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let session = try decoder.decode(AuthSession.self, from: data)
        XCTAssertEqual(session.expiresAt, 1790000000)
    }

    func testSkillMentionsDoNotMatchPartialWords() {
        let job = Job(id: "test", title: "Designer", company: "Example", location: "", url: "",
                      description: "Use Figma for accessible design and prototyping.", status: "saved")
        XCTAssertEqual(job.skillMatches(["Figma", "Go", "Typing", "Design"]), ["Figma", "Design"])
    }

    func testAccountContractDecodesServerSnakeCase() throws {
        let json = #"{"id":"test","purchase_token":"7C99CE98-CDA1-4FA1-985F-682CD2228834","balance":45,"profile":{"name":"Alex","headline":"Designer","location":"Remote","skills":[],"experience":"Work","ai_consent":true},"active_subscriptions":[],"billing_available":true,"tailoring_available":true,"tailor_cost":5}"#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let account = try decoder.decode(Account.self, from: Data(json.utf8))
        XCTAssertEqual(account.balance, 45)
        XCTAssertTrue(account.profile.aiConsent)
        XCTAssertEqual(account.tailorCost, 5)
    }
}
