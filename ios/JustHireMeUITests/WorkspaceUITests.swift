import XCTest

final class WorkspaceUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
    }

    @MainActor
    func testOnboardingAndDemoNavigation() throws {
        app.launch()
        let explore = app.buttons["demo.explore"]
        reveal(explore)
        capture("01-onboarding")
        explore.tap()
        XCTAssertTrue(app.tabBars.buttons["Workspace"].waitForExistence(timeout: 10))
        capture("02-workspace")

        app.tabBars.buttons["Credits"].tap()
        XCTAssertTrue(app.staticTexts["Available credits"].waitForExistence(timeout: 5))
        capture("03-credit-plans")
        // Demo never offers a live purchase button or an invented balance.
        XCTAssertFalse(app.buttons["Restore purchases"].exists)

        app.tabBars.buttons["Drafts"].tap()
        XCTAssertTrue(app.staticTexts["Your words, made more focused"].waitForExistence(timeout: 5))
        capture("04-drafts-empty")

        app.tabBars.buttons["Profile"].tap()
        let name = app.textFields["profile.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        XCTAssertEqual(name.value as? String, "Alex Morgan")
        capture("05-profile")
        reveal(app.buttons["profile.save"])
        XCTAssertFalse(app.buttons["profile.save"].isEnabled)
    }

    @MainActor
    func testCreateJobAndTrackInterviewInDemo() throws {
        app.launchArguments.append("--demo")
        app.launch()
        let add = app.buttons["jobs.add"]
        reveal(add)
        add.tap()
        let title = app.textFields["job.form.title"]
        XCTAssertTrue(title.waitForExistence(timeout: 5))
        title.tap()
        title.typeText("UX Researcher")
        let company = app.textFields["job.form.company"]
        company.tap()
        company.typeText("Test Company")
        let description = app.textViews["job.form.description"]
        reveal(description)
        description.tap()
        description.typeText("Lead research and accessibility studies for a collaborative team building useful products.")
        capture("06-add-opportunity")
        app.buttons["job.form.save"].tap()

        let savedTitle = app.staticTexts["UX Researcher"].firstMatch
        reveal(savedTitle)
        savedTitle.tap()
        let status = app.buttons["job.status"]
        reveal(status)
        status.tap()
        app.buttons["status.interviewing"].tap()
        let updated = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", "Interviewing"), object: status)
        XCTAssertEqual(XCTWaiter.wait(for: [updated], timeout: 5), .completed)
        capture("07-interview-status")
    }

    @MainActor
    func testDemoDraftingIsDisabled() throws {
        app.launchArguments.append("--demo")
        app.launch()
        let job = app.buttons["job.demo-1"]
        reveal(job)
        job.tap()
        let tailor = app.buttons["job.tailor"]
        reveal(tailor)
        XCTAssertFalse(tailor.isEnabled)
        XCTAssertTrue(app.staticTexts["Application drafting is available after sign-in."].exists)
        capture("08-job-detail")
    }

    @MainActor
    private func reveal(_ element: XCUIElement, file: StaticString = #filePath, line: UInt = #line) {
        for _ in 0..<8 {
            if element.exists && (element.isHittable || (!element.isEnabled && app.frame.intersects(element.frame))) { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists && (element.isHittable || (!element.isEnabled && app.frame.intersects(element.frame))),
                      "Expected element is not reachable: \(element)", file: file, line: line)
    }

    @MainActor
    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
