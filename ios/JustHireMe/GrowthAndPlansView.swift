import SwiftUI

struct GrowthView: View {
    @Environment(NotebookModel.self) private var book
    private var rejected: Int { book.applications.filter { $0.stage == .rejected }.count }
    var body: some View {
        NotebookPage {
            NotebookHeading(chapter: "04 / Learning", title: "What to work on", subtitle: "Skills to practise for the roles you’re interested in.", tint: NotebookInk.butter)
            if let message = book.connectionMessage { InlineMessage(text: message) }
            NotebookCard(tint: NotebookInk.butter) {
                VStack(alignment: .leading, spacing: 13) {
                    HStack { Image(systemName: "bookmark").font(.system(size: 20, weight: .regular)); Spacer(); NotebookTag(text: "Suggested focus", tint: Theme.card.opacity(0.7)) }
                    Text(book.gaps.first ?? "Keep your profile up to date").font(Theme.heading(21))
                    Text(book.gaps.isEmpty ? "Add more profile details and recommended roles to reveal useful skill gaps." : "These are skills listed in suggested roles that aren’t yet in your profile. They are learning opportunities, not a hiring prediction.")
                        .font(Theme.sans(13)).foregroundStyle(Theme.copy)
                    Text("\(book.completedLessons.count) completed").font(Theme.sans(12))
                }
            }
            ForEach(Array(book.gaps.enumerated()), id: \.element) { index, skill in
                learningCard(skill, index: index)
            }
            if rejected > 0 {
                NotebookCard(tint: NotebookInk.peach) {
                    VStack(alignment: .leading, spacing: 14) {
                        Label("Application feedback", systemImage: "text.bubble").font(Theme.sans(12, bold: true))
                        Text("Review a case study").font(Theme.heading(19))
                        Text("\(rejected) rejected application\(rejected == 1 ? "" : "s") in your history. No employer feedback is available, so we won’t guess why. Try improving one case study: show the problem, your decisions, and the outcome.")
                            .font(Theme.sans(13)).foregroundStyle(Theme.copy)
                        Link("Read: choosing UX research methods", destination: URL(string: "https://www.nngroup.com/articles/ux-research-cheat-sheet/")!).font(Theme.sans(13, bold: true))
                    }
                }
            }
        }.navigationTitle("Grow")
    }
    private func learningCard(_ skill: String, index: Int) -> some View {
        let count = book.roles.filter { $0.requirements.contains(skill) }.count
        let done = book.completedLessons.contains(skill)
        let resource = LearningResource.forSkill(skill)
        return NotebookCard(ruled: true) {
            VStack(alignment: .leading, spacing: 15) {
                HStack { NotebookTag(text: "Requested by \(count) role\(count == 1 ? "" : "s")", tint: NotebookInk.color(index)); Spacer(); Image(systemName: done ? "checkmark.circle.fill" : "bookmark").foregroundStyle(Theme.accent) }
                Text(skill).font(Theme.heading(20))
                Text(resource.exercise)
                    .font(Theme.sans(14)).foregroundStyle(Theme.copy)
                Link(destination: resource.url) {
                    Label(resource.title, systemImage: "arrow.up.right").font(Theme.sans(13, bold: true))
                }
                Button(done ? "Completed · mark unfinished" : "Mark this step complete") {
                    if book.isConnected { Task { do { try await book.toggleLesson(skill) } catch { book.connectionMessage = error.localizedDescription } } }
                    else if done { book.completedLessons.remove(skill) } else { book.completedLessons.insert(skill) }
                }.font(Theme.sans(12)).accessibilityIdentifier("learn.\(skill)")
            }
        }
    }
}

struct ApplicationPlansView: View {
    @Environment(NotebookModel.self) private var book
    @State private var selected: ApplicationPlan = .monthly
    @State private var confirm = false
    @State private var message: String?
    var body: some View {
        NotebookPage {
            NotebookHeading(chapter: "05 / Plan", title: "Application plans", subtitle: "Pay per application, or choose a weekly or monthly allowance.", tint: NotebookInk.pink)
            NotebookCard(tint: NotebookInk.mint) {
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        Text("\(book.remaining)").font(Theme.sans(32, bold: true)).accessibilityIdentifier("allowance.remaining")
                        VStack(alignment: .leading, spacing: 4) {
                            Text("applications left").font(Theme.sans(15, bold: true))
                            Text(book.isPreview ? "Sample allowance · \(book.activePlan.cadence)" : "Connect your account plan").font(Theme.sans(11)).foregroundStyle(Theme.copy)
                        }
                    }
                    ProgressView(value: Double(max(0, book.allowance-book.remaining)), total: Double(max(1, book.allowance))).tint(Theme.accent)
                    Text("\(max(0, book.allowance-book.remaining)) of \(book.allowance) applications used").font(Theme.mono(10))
                }
            }
            ForEach(ApplicationPlan.allCases) { plan in
                Button { selected = plan; message = nil } label: {
                    NotebookCard(tint: selected == plan ? NotebookInk.lavender : Theme.card) {
                        VStack(alignment: .leading, spacing: 13) {
                            HStack {
                                Text(plan.name).font(Theme.heading(20))
                                Spacer()
                                Image(systemName: selected == plan ? "checkmark.circle.fill" : "circle").foregroundStyle(Theme.accent)
                            }
                            HStack(alignment: .firstTextBaseline, spacing: 7) {
                                Text("\(plan.count)").font(Theme.sans(28, bold: true))
                                Text("application\(plan.count == 1 ? "" : "s") \(plan.cadence)").font(Theme.sans(14))
                            }
                            Text(plan == .single ? "One purchase, one application. No subscription." : "One-tap apply & auto-apply share this allowance.").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                            Text(plan == .single ? "No recurring charge." : "Renews \(plan == .weekly ? "weekly" : "monthly"). Cancel through Apple.").font(Theme.sans(11)).foregroundStyle(Theme.copy)
                        }
                    }
                }.buttonStyle(.plain).accessibilityIdentifier("applications-plan.\(plan.id)")
                    .accessibilityAddTraits(selected == plan ? .isSelected : [])
            }
            NotebookButton(title: book.isPreview ? "Try this plan in preview" : "Plans available after billing setup", symbol: "ticket") { confirm = true }
                .disabled(!book.isPreview).accessibilityIdentifier("applications-plan.choose")
            Text("Final prices and payment terms will come from the App Store. Preview selections never charge you or start a subscription.")
                .font(Theme.sans(12)).foregroundStyle(Theme.copy)
            if let message { InlineMessage(text: message).accessibilityIdentifier("applications-plan.success") }
            LegalLinks()
        }.navigationTitle("Your plan")
            .confirmationDialog("Try \(selected.count) application\(selected.count == 1 ? "" : "s") \(selected.cadence)?", isPresented: $confirm, titleVisibility: .visible) {
                Button("Use sample allowance") {
                    do { try book.choose(selected); message = "Your preview now has \(book.remaining) applications available. No payment was made." }
                    catch { message = error.localizedDescription }
                }
            } message: { Text("A recurring sample plan starts a fresh allowance. A single application adds one. This is a preview only.") }
    }
}
