import XCTest

class WorkspaceUITests: XCTestCase {
    var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "--demo"]
    }
    @MainActor func testProfileImportAndInlineEditing() {
        app.launch()
        reveal(app.buttons["notebook.import"])
        capture("01-profile-notebook")
        app.buttons["notebook.import"].tap()
        reveal(app.buttons["import.example"])
        app.buttons["import.example"].tap()
        reveal(app.buttons["import.accept"])
        capture("02-organized-import")
        app.buttons["import.accept"].tap()
        XCTAssertTrue(app.navigationBars["My notebook"].waitForExistence(timeout: 5))
        reveal(app.buttons["section.edit.about"])
        app.buttons["section.edit.about"].tap()
        XCTAssertTrue(app.textViews["section.editor.about"].waitForExistence(timeout: 5))
        app.textViews["section.editor.about"].tap()
        app.textViews["section.editor.about"].typeText(" Personal note.")
        app.buttons["section.edit.about"].tap()
        XCTAssertFalse(app.textViews["section.editor.about"].exists)
    }
    @MainActor func testApplyAndTrackRejectedOutcome() {
        app.launch()
        app.tabBars.buttons["For You"].tap()
        reveal(app.buttons["match.match-1"])
        capture("03-recommendations")
        app.buttons["match.match-1"].tap()
        capture("04-role-details")
        app.buttons["match.apply"].tap()
        XCTAssertTrue(app.staticTexts["Submitted"].waitForExistence(timeout: 5))
        capture("05-application-submitted")
        reveal(app.buttons["application.response"])
        app.buttons["application.response"].tap()
        app.buttons["outcome.rejected"].tap()
        XCTAssertTrue(app.staticTexts["No feedback provided"].waitForExistence(timeout: 5))
        app.tabBars.buttons["Applications"].tap()
        capture("06-outcome-chart")
        reveal(app.buttons["application.match-1"])
        XCTAssertTrue(app.buttons["application.match-1"].isHittable)
    }
    @MainActor func testPlanAndBoundedAutomation() {
        app.launch()
        app.tabBars.buttons["Plan"].tap()
        reveal(app.buttons["applications-plan.monthly"])
        app.buttons["applications-plan.monthly"].tap()
        reveal(app.buttons["applications-plan.choose"])
        app.buttons["applications-plan.choose"].tap()
        app.buttons["Use sample allowance"].tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "40 applications available")).firstMatch.waitForExistence(timeout: 5))
        capture("07-application-plan")
        app.tabBars.buttons["For You"].tap()
        app.buttons["matches.automation"].tap()
        reveal(app.switches["auto.enable"])
        app.switches["auto.enable"].tap()
        reveal(app.buttons["auto.run"])
        app.buttons["auto.run"].tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "No employers were contacted")).firstMatch.waitForExistence(timeout: 5))
        capture("08-auto-apply-rules")
    }
    @MainActor func testGrowthAndDarkMode() {
        app.launchArguments.append("--appearance-dark")
        app.launch()
        capture("09-profile-dark")
        app.tabBars.buttons["Grow"].tap()
        reveal(app.buttons["learn.Design systems"])
        capture("10-growth-plan")
        app.buttons["learn.Design systems"].tap()
        XCTAssertTrue(app.buttons["learn.Design systems"].label.contains("Completed"))
    }
    @MainActor func testOnboardingAndLargeText() {
        app.launchArguments = ["--ui-testing", "--large-text"]
        app.launch()
        reveal(app.buttons["demo.explore"])
        app.buttons["demo.explore"].tap()
        XCTAssertTrue(app.navigationBars["My notebook"].waitForExistence(timeout: 5))
        reveal(app.buttons["notebook.import"])
        capture("11-profile-large-text")
        XCTAssertTrue(app.buttons["notebook.import"].isEnabled)
    }
    @MainActor func reveal(_ element: XCUIElement, file: StaticString = #filePath, line: UInt = #line) {
        for _ in 0..<12 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists && element.isHittable, "Element is not reachable: \(element)", file: file, line: line)
    }
    @MainActor func capture(_ name: String) {
        let a = XCTAttachment(screenshot: app.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a)
    }
}

final class WalkthroughUITests: XCTestCase {
    @MainActor func testWalkthrough() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--ui-testing", "--demo"]; app.launch()
        XCTAssertTrue(app.navigationBars["My notebook"].waitForExistence(timeout: 10))
        pause()
        reveal(app.buttons["notebook.import"], in: app); app.buttons["notebook.import"].tap()
        reveal(app.buttons["import.example"], in: app); app.buttons["import.example"].tap()
        reveal(app.buttons["import.accept"], in: app); pause(); app.buttons["import.accept"].tap()
        app.swipeUp(); pause()
        app.tabBars.buttons["For You"].tap(); pause()
        reveal(app.buttons["match.match-2"], in: app); app.buttons["match.match-2"].tap(); pause()
        app.buttons["match.apply"].tap(); pause()
        app.tabBars.buttons["Applications"].tap(); pause()
        app.tabBars.buttons["Grow"].tap(); app.swipeUp(); pause()
        app.tabBars.buttons["Plan"].tap(); pause(); app.swipeUp(); pause()
    }
    @MainActor private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<10 { if element.exists && element.isHittable { return }; app.swipeUp() }
        XCTAssertTrue(element.isHittable)
    }
    private func pause() { Thread.sleep(forTimeInterval: 2.5) }
}
