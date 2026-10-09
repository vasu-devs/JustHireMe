import XCTest
import UIKit
@testable import JustHireMe

final class ModelsTests: XCTestCase {
    @MainActor
    func testDesktopBrandFontsAreBundledAndRegistered() throws {
        for name in ["InstrumentSerif-Regular", "InstrumentSerif-Italic", "InstrumentSans-Regular",
                     "InstrumentSans-Bold", "GeistMono-Regular", "BricolageGrotesque-Bold"] {
            XCTAssertNotNil(UIFont(name: name, size: 20), "Missing bundled font: \(name)")
        }
    }

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

    @MainActor
    func testPreviewFlowDebitsOnceAndResetsWithoutCloudState() async throws {
        let model = AppModel()
        model.demo()
        var profile = model.profile
        profile.name = "Taylor"
        try await model.saveProfile(profile)
        let first = try model.previewApplication(for: model.jobs[0])
        XCTAssertTrue(first.text.contains("Taylor"))
        XCTAssertEqual(model.balance, 25)
        XCTAssertEqual(try model.previewApplication(for: model.jobs[0]).id, first.id)
        XCTAssertEqual(model.balance, 25)
        try model.saveEdit("My edited application", for: first)
        XCTAssertEqual(model.text(for: first), "My edited application")
        try await model.update(model.jobs[0], status: "applied")
        XCTAssertEqual(model.jobs[0].status, "applied")
        try model.previewPurchase(.monthly)
        XCTAssertEqual(model.balance, 175)
        XCTAssertNil(model.account)
        await model.signOut()
        XCTAssertTrue(model.draftEdits.isEmpty)
        XCTAssertThrowsError(try model.previewPurchase(.monthly))
        model.demo()
        XCTAssertEqual(model.balance, 30)
        XCTAssertEqual(model.profile.name, "Alex Morgan")
        XCTAssertTrue(model.drafts.isEmpty)
    }

    @MainActor
    func testPreviewInsufficientBalanceAndIncompleteProfileDoNotCreateDrafts() throws {
        let model = AppModel()
        model.demo()
        model.demoBalance = 0
        XCTAssertThrowsError(try model.previewApplication(for: model.jobs[0]))
        XCTAssertTrue(model.drafts.isEmpty)
        XCTAssertTrue(model.ledger.isEmpty)
        try model.previewPurchase(.topUp)
        model.demoProfile.experience = "  "
        XCTAssertThrowsError(try model.previewApplication(for: model.jobs[0]))
        XCTAssertEqual(model.balance, 50)
    }

    func testDeviceDraftEditsAreScopedToAccount() throws {
        let first = UUID().uuidString
        let second = UUID().uuidString
        defer { try? DraftEditStorage.remove(accountID: first); try? DraftEditStorage.remove(accountID: second) }
        try DraftEditStorage.save(["draft": "Private edit"], accountID: first)
        XCTAssertEqual(DraftEditStorage.load(accountID: first)["draft"], "Private edit")
        XCTAssertTrue(DraftEditStorage.load(accountID: second).isEmpty)
        try DraftEditStorage.remove(accountID: first)
        XCTAssertTrue(DraftEditStorage.load(accountID: first).isEmpty)
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

    func testValidationFailureMessagesNameTheField() {
        let body = Data(#"{"detail":[{"loc":["body","candidate","resume_text"],"msg":"String should have at least 40 characters","type":"string_too_short"}]}"#.utf8)
        XCTAssertEqual(APIClient.failureMessage(status: 422, data: body), "resume text: String should have at least 40 characters")
        XCTAssertEqual(APIClient.failureMessage(status: 409, data: Data(#"{"detail":"Pause your current campaign first."}"#.utf8)), "Pause your current campaign first.")
        XCTAssertEqual(APIClient.failureMessage(status: 502, data: Data()), "The request could not be completed (502). Please retry.")
        XCTAssertTrue(AppError.unauthorized.isUnauthorized)
        XCTAssertEqual(AppError.http(422, "x").status, 422)
        XCTAssertEqual(AppError.unauthorized.errorDescription, "Your session has expired. Please sign in again.")
    }

    func testRequiredAnswersSupportChoiceAndConsentQuestions() throws {
        let json = #"[{"label":"Are you legally authorized to work in the EU?","type":"radio","required":true,"options":["Yes","No"]},{"label":"I certify the information is accurate","type":"checkbox","required":false,"options":[]},{"label":"Portfolio link","type":"url","required":true,"options":[]},{"label":"Which office?","required":true,"fields":[{"name":"q1","type":"multi_value_single_select","values":[{"label":"Berlin","value":1},{"label":"Remote","value":2}]}]},{"label":"Upload a video","type":"file","options":[]},{"label":"","type":"text"}]"#
        let values = try JSONDecoder().decode([JSONValue].self, from: Data(json.utf8))
        let answers = values.compactMap(RequiredAnswer.init)
        XCTAssertEqual(answers.count, 5)
        XCTAssertEqual(answers[0].options, ["Yes", "No"])
        XCTAssertTrue(answers[0].supported && answers[0].required)
        XCTAssertEqual(answers[1].options, ["Yes", "No"])
        XCTAssertTrue(answers[1].supported)
        XCTAssertFalse(answers[1].required)
        XCTAssertTrue(answers[2].supported && answers[2].options.isEmpty)
        XCTAssertEqual(answers[3].options, ["Berlin", "Remote"])
        XCTAssertTrue(answers[3].supported)
        XCTAssertFalse(answers[4].supported)
    }
}
