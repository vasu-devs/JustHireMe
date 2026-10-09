import SwiftUI

struct OverviewView: View {
    @Environment(AppModel.self) private var model
    @Binding var tab: AppTab
    @State private var showPlans = false
    private var nextRole: Job? { model.jobs.first { $0.status == "saved" } }
    private var firstName: String { model.profile.name.split(separator: " ").first.map(String.init) ?? "there" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack {
                    Eyebrow(text: "A little focus. A big next chapter.")
                    Spacer(minLength: 12)
                    Button { showPlans = true } label: {
                        Label("\(model.balance)", systemImage: "sparkles")
                            .font(Theme.sans(14, bold: true)).padding(12)
                            .background(Theme.card, in: Capsule())
                    }.accessibilityLabel("\(model.balance) \(model.isDemo ? "demo " : "")credits. View plans")
                        .accessibilityIdentifier("home.plans")
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text("Your next move,\n\(firstName).").font(Theme.display(42))
                        .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("journal.headline")
                    Text("Good work starts with one good opportunity.")
                        .font(Theme.sans(15)).foregroundStyle(Theme.copy)
                }
                if let message = model.message {
                    InlineMessage(text: message)
                    Button("Try again") { Task { await model.reload() } }
                }
                if let role = nextRole {
                    VStack(alignment: .leading, spacing: 18) {
                        HStack {
                            Label("YOUR NEXT STEP", systemImage: "arrow.up.right").font(Theme.mono(11))
                            Spacer()
                            Text("01").font(Theme.mono(12))
                        }.foregroundStyle(Theme.accent)
                        Text(role.title).font(Theme.heading(25))
                        Text("\(role.company) · \(role.location)").font(Theme.sans(14)).foregroundStyle(Theme.copy)
                        Text("\(role.skillMatches(model.profile.skills).count) of your skills appear in this role. Take a closer look.")
                            .font(Theme.sans(14)).foregroundStyle(Theme.copy)
                        NavigationLink(value: role) {
                            HStack { Text("Explore this role"); Spacer(); Image(systemName: "arrow.right") }
                                .font(Theme.sans(15, bold: true)).padding(17)
                                .foregroundStyle(Theme.buttonInk).background(Theme.accent, in: Capsule())
                        }.accessibilityIdentifier("home.next-role")
                    }.padding(22).journalCard(tint: Theme.green)
                } else {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Make room for what’s next.").font(Theme.display(28))
                        Text("Save a role you like. We’ll help you take the next step.").foregroundStyle(Theme.copy)
                        ActionButton(title: "Find your next role") { tab = .pipeline }
                    }.padding(22).journalCard(tint: Theme.green)
                }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 12) { metrics }
                    VStack(spacing: 12) { metrics }
                }
                HStack {
                    Text("Keep things moving").font(Theme.heading(21))
                    Spacer()
                    Button("All roles") { tab = .pipeline }.font(Theme.sans(13, bold: true))
                        .accessibilityIdentifier("overview.all-roles")
                }
                ForEach(model.jobs.filter { $0.status == "interviewing" }.prefix(2)) { job in
                    NavigationLink(value: job) {
                        HStack(spacing: 14) {
                            Image(systemName: "bubble.left.and.bubble.right").font(.title2)
                                .frame(width: 48, height: 48).background(Theme.yellow.opacity(0.35), in: RoundedRectangle(cornerRadius: 14))
                            VStack(alignment: .leading, spacing: 5) {
                                Text("Interviewing with \(job.company)").font(Theme.sans(15, bold: true))
                                Text(job.title).font(Theme.sans(13)).foregroundStyle(Theme.copy)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption)
                        }.padding(18).journalCard()
                    }.buttonStyle(.plain)
                }
                Button { tab = .profile } label: {
                    HStack(spacing: 14) {
                        Image(systemName: "person.crop.circle.badge.checkmark").font(.title2)
                        VStack(alignment: .leading, spacing: 5) {
                            Text("Your experience is the starting point.").font(Theme.sans(15, bold: true))
                            Text("Keep your profile ready for your next application.").font(Theme.sans(13)).foregroundStyle(Theme.copy)
                        }
                        Spacer()
                        Image(systemName: "arrow.right")
                    }.padding(18).journalCard(tint: Theme.pink)
                }.buttonStyle(.plain)
            }.padding(22).frame(maxWidth: 720).frame(maxWidth: .infinity)
        }.journalScreen().navigationTitle("JustHireMe").navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Job.self) { JobDetailView(job: $0) }
            .refreshable { await model.reload() }
            .sheet(isPresented: $showPlans) { NavigationStack { PlansView().toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showPlans = false } } } } }
    }

    @ViewBuilder private var metrics: some View {
        metric("Saved roles", count: model.jobs.filter { $0.status == "saved" }.count, symbol: "bookmark", tint: Theme.blue, destination: .pipeline)
        metric("Applications", count: model.drafts.count, symbol: "doc.text", tint: Theme.pink, destination: .drafts)
        metric("Interviews", count: model.jobs.filter { $0.status == "interviewing" }.count, symbol: "bubble.left", tint: Theme.yellow, destination: .pipeline)
    }

    private func metric(_ title: String, count: Int, symbol: String, tint: Color, destination: AppTab) -> some View {
        Button { tab = destination } label: {
            VStack(alignment: .leading, spacing: 12) {
                Image(systemName: symbol).foregroundStyle(Theme.accent)
                Text(count.formatted()).font(Theme.display(32))
                Text(title).font(Theme.sans(12)).fixedSize(horizontal: true, vertical: false)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(16).journalCard(tint: tint)
        }.buttonStyle(.plain)
    }
}
