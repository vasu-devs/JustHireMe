import XCTest
import Foundation

final class ConnectedWalkthroughUITests: XCTestCase {
    @MainActor func testConnectedJourneyWithVasudevProfile() async throws {
        continueAfterFailure = false
        let bootstrap: Bootstrap
        do { bootstrap = try await readFixture("bootstrap", as: Bootstrap.self) }
        catch { XCTFail("The connected walkthrough requires its loopback E2E backend: \(error)"); throw error }
        let app = XCUIApplication()
        app.launchArguments = ["--connected-testing", "--ui-testing"]
        app.launchEnvironment["JHM_TEST_TOKEN"] = bootstrap.token
        app.launch()
        XCTAssertTrue(app.staticTexts[bootstrap.name].waitForExistence(timeout: 25))
        capture(app, "01-connected-profile")
        pause()

        reveal(app.buttons["notebook.import"], in: app)
        app.buttons["notebook.import"].tap()
        reveal(app.textViews["import.notes"], in: app)
        app.textViews["import.notes"].tap()
        app.textViews["import.notes"].typeText(bootstrap.markdown)
        app.buttons["import.dismiss-keyboard"].tap()
        reveal(app.buttons["import.organize"], in: app)
        app.buttons["import.organize"].tap()
        reveal(app.buttons["import.accept"], in: app)
        capture(app, "02-profile-import")
        pause()
        app.buttons["import.accept"].tap()
        for _ in 0..<5 { app.swipeDown() }
        XCTAssertTrue(app.buttons["connected.save"].waitForExistence(timeout: 10))
        app.buttons["connected.save"].tap()
        XCTAssertTrue(app.staticTexts["Saved to your account"].waitForExistence(timeout: 15))
        capture(app, "03-saved-profile")
        // Relaunch must restore the saved sections from the API, not demo memory.
        app.terminate(); app.launch()
        XCTAssertTrue(app.staticTexts[bootstrap.name].waitForExistence(timeout: 25))
        reveal(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "Lovely Professional University")).firstMatch, in: app)
        capture(app, "04-persisted-education")
        pause()

        app.tabBars.buttons["For You"].tap()
        let ai = try XCTUnwrap(bootstrap.jobs["AI Engineer"])
        XCTAssertTrue(app.buttons["match.\(ai)"].waitForExistence(timeout: 30))
        capture(app, "05-matched-jobs")
        pause()
        app.buttons["match.\(ai)"].tap()
        pause()
        app.buttons["match.apply"].tap()
        XCTAssertTrue(app.navigationBars["Application"].waitForExistence(timeout: 10))
        capture(app, "06-queued-application")
        XCTAssertTrue(app.staticTexts["Submitted"].waitForExistence(timeout: 35))
        capture(app, "07-confirmed-submission")
        reveal(app.buttons["connected.resume"], in: app)
        app.buttons["connected.resume"].tap()
        XCTAssertTrue(app.navigationBars["Your résumé"].waitForExistence(timeout: 10))
        capture(app, "08-generated-resume")
        pause()
        app.buttons["Done"].tap()
        reveal(app.buttons["connected.outcome"], in: app)
        app.buttons["connected.outcome"].tap()
        app.buttons["Interview"].tap()
        for _ in 0..<4 { app.swipeDown() }
        XCTAssertTrue(app.staticTexts["Interviewing"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Applications"].tap()
        capture(app, "09-application-tracker")
        pause()

        app.tabBars.buttons["For You"].tap()
        // Return from the first application's navigation stack to the feed.
        returnToFeed(app)
        let fullStack = try XCTUnwrap(bootstrap.jobs["Full Stack Engineer"])
        reveal(app.buttons["match.\(fullStack)"], in: app)
        app.buttons["match.\(fullStack)"].tap()
        app.buttons["match.apply"].tap()
        XCTAssertTrue(app.staticTexts["Needs attention"].waitForExistence(timeout: 35))
        let answer = app.descendants(matching: .any).matching(identifier: "answer.Portfolio link").firstMatch
        reveal(answer, in: app)
        capture(app, "10-missing-answer")
        answer.tap()
        answer.typeText("https://siddhvasudev.com")
        app.buttons["answer.dismiss-keyboard"].tap()
        reveal(app.buttons["connected.retry"], in: app)
        app.buttons["connected.retry"].tap()
        app.buttons["Authorize retry"].tap()
        for _ in 0..<4 { app.swipeDown() }
        XCTAssertTrue(app.staticTexts["Submitted"].waitForExistence(timeout: 35))
        capture(app, "11-retried-submission")

        app.tabBars.buttons["For You"].tap()
        returnToFeed(app)
        for _ in 0..<5 { app.swipeDown() }
        app.buttons["matches.automation"].tap()
        reveal(app.steppers["campaign.daily"], in: app)
        app.buttons["campaign.daily-Increment"].tap()
        reveal(app.buttons["campaign.start"], in: app)
        app.buttons["campaign.start"].tap()
        app.buttons["Authorize auto-apply"].tap()
        XCTAssertTrue(app.buttons["campaign.pause"].waitForExistence(timeout: 15))
        // Wait for the actual backend campaign worker to submit the remaining fixture role.
        var evidence = try await readFixture("evidence", as: Evidence.self)
        for _ in 0..<20 where evidence.submitted < 3 {
            try await Task.sleep(for: .seconds(2))
            evidence = try await readFixture("evidence", as: Evidence.self)
        }
        XCTAssertEqual(evidence.submitted, 3)
        app.buttons["campaign.pause"].tap()
        XCTAssertTrue(app.staticTexts["Paused"].waitForExistence(timeout: 15))
        capture(app, "12-auto-apply-paused")
        app.buttons["Done"].tap()

        app.tabBars.buttons["Grow"].tap()
        reveal(app.buttons["learn.Kubernetes"], in: app)
        app.buttons["learn.Kubernetes"].tap()
        XCTAssertTrue(app.buttons["learn.Kubernetes"].waitForExistence(timeout: 10))
        capture(app, "13-learning")
        pause()
        app.tabBars.buttons["Plan"].tap()
        capture(app, "14-server-plans")
        reveal(app.buttons["connected.purchase.justhireme.pro.monthly"], in: app)
        app.buttons["connected.purchase.justhireme.pro.monthly"].tap()
        XCTAssertTrue(app.staticTexts["Test allowance added. No payment was made."].waitForExistence(timeout: 15))
        capture(app, "15-test-purchase")
        pause()

        evidence = try await readFixture("evidence", as: Evidence.self)
        XCTAssertEqual(evidence.submitted, 3)
        XCTAssertEqual(evidence.employerCalls, 3)
        XCTAssertEqual(evidence.uniqueEmployerCalls, 3)
        XCTAssertEqual(evidence.resumeCount, 3)
        XCTAssertEqual(evidence.emails, 3)
        XCTAssertEqual(evidence.balance, 185) // 50 seed - 15 successful applications + 150 test purchase.
        XCTAssertTrue(evidence.workerErrors.isEmpty)
        app.terminate(); app.launch()
        XCTAssertTrue(app.staticTexts[bootstrap.name].waitForExistence(timeout: 25))
        app.tabBars.buttons["Grow"].tap()
        reveal(app.buttons["learn.Kubernetes"], in: app)
        XCTAssertTrue(app.buttons["learn.Kubernetes"].label.contains("Completed"))
        capture(app, "16-persisted-learning")
    }

    struct Bootstrap: Decodable { var token: String; var markdown: String; var name: String; var jobs: [String: String] }
    struct Evidence: Decodable { var submitted: Int; var employerCalls: Int; var uniqueEmployerCalls: Int; var resumeCount: Int; var emails: Int; var balance: Int; var workerErrors: [String] }
    private func readFixture<T: Decodable>(_ path: String, as: T.Type) async throws -> T {
        let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:8769/__test/\(path)")!)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
    @MainActor private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<16 { if element.exists && element.isHittable { return }; app.swipeUp() }
        XCTAssertTrue(element.isHittable, "Unreachable element: \(element)")
    }
    @MainActor private func returnToFeed(_ app: XCUIApplication) {
        for _ in 0..<3 { if app.navigationBars["For you"].exists { return }; app.navigationBars.buttons.firstMatch.tap() }
        XCTAssertTrue(app.navigationBars["For you"].exists)
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }
    private func pause() { Thread.sleep(forTimeInterval: 2) }
}
