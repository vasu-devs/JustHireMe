import XCTest
@testable import JustHireMe

final class NotebookTests: XCTestCase {
    func testMarkdownSectionsAndBulletSkills() throws {
        let result = ProfileTextParser.parse("# Skills\n- Figma\n* Research\n## Experience\nDesigner, 2022–present\n## Projects\nNotebook", filename: "profile.md")
        XCTAssertEqual(result.sections.count, 3)
        var profile = NotebookProfile()
        profile[.skills] = try XCTUnwrap(result.sections["skills"])
        XCTAssertEqual(profile.skills, ["Figma", "Research"])
        XCTAssertFalse(result.pending)
    }
    @MainActor func testImportPreservesEditsAndDuplicateSections() throws {
        let model = NotebookModel(); model.reset(preview: true)
        model.profile[.projects] = "My manually edited project"
        let imported = ProfileTextParser.parse("# Projects\nNew project", filename: "new.md")
        try model.add(imported); try model.add(imported)
        XCTAssertEqual(model.profile[.projects], "My manually edited project\n\nNew project")
        XCTAssertThrowsError(try model.add(ProfileTextParser.parse(" \n", filename: "empty.md")))
    }
    @MainActor func testOneTapApplicationDebitsOnceAndTracksOutcome() throws {
        let model = NotebookModel(); model.reset(preview: true)
        let role = NotebookSamples.roles[0]
        let first = try model.apply(role)
        XCTAssertEqual(model.remaining, 6)
        XCTAssertEqual(try model.apply(role).id, first.id)
        XCTAssertEqual(model.remaining, 6)
        model.update(first, stage: .rejected)
        XCTAssertEqual(model.applications.first?.stage, .rejected)
        XCTAssertEqual(model.applications.first?.events.last, "Preview outcome updated to rejected")
    }
    @MainActor func testAutoApplyRespectsDailyCapRoleLocationAndAllowance() throws {
        let model = NotebookModel(); model.reset(preview: true)
        model.autoEnabled = true; model.autoDailyLimit = 1
        XCTAssertEqual(try model.runAutomationPreview(), 1)
        XCTAssertEqual(try model.runAutomationPreview(), 0)
        XCTAssertFalse(model.eligibleForAuto(NotebookSamples.roles[2]))
        model.autoDailyLimit = 5; model.remaining = 0
        XCTAssertEqual(try model.runAutomationPreview(), 0)
        model.autoEnabled = false
        XCTAssertEqual(try model.runAutomationPreview(), 0)
    }
    @MainActor func testPlansAndServiceBoundary() throws {
        let model = NotebookModel()
        XCTAssertEqual(model.remaining, 0)
        XCTAssertThrowsError(try model.apply(NotebookSamples.roles[0]))
        XCTAssertThrowsError(try model.choose(.monthly))
        model.reset(preview: true)
        try model.choose(.monthly); XCTAssertEqual(model.remaining, 40)
        try model.choose(.single); XCTAssertEqual(model.remaining, 41)
        model.remaining = 0
        XCTAssertThrowsError(try model.apply(NotebookSamples.roles[0]))
        model.remaining = 1; model.profile.name = ""
        XCTAssertThrowsError(try model.apply(NotebookSamples.roles[0]))
        XCTAssertEqual(model.remaining, 1)
        model.reset(preview: false)
        XCTAssertTrue(model.applications.isEmpty)
        XCTAssertTrue(model.sources.isEmpty)
        XCTAssertFalse(model.autoEnabled)
    }
    @MainActor func testSkillGapsChangeWithProfile() {
        let model = NotebookModel(); model.reset(preview: true)
        XCTAssertEqual(model.gaps, ["Design systems", "JavaScript"])
        model.profile[.skills] += ", Design systems"
        XCTAssertEqual(model.gaps, ["JavaScript"])
        XCTAssertEqual(NotebookSamples.roles[0].score(model.profile), 100)
    }
}
