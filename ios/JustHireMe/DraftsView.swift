import SwiftUI

struct DraftsView: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        List {
            Section {
                Text("Thoughtful applications, ready for your review.").font(.system(.title2, design: .serif))
                    .listRowBackground(Color.clear)
            }
            if model.drafts.isEmpty {
                ContentUnavailableView("Your words, made more focused", systemImage: "doc.text",
                    description: Text("Prepare an application from a saved opportunity. Your drafts will appear here."))
                    .listRowBackground(Color.clear)
            }
            ForEach(model.drafts) { draft in
                NavigationLink {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            InlineMessage(text: "Review names, dates, qualifications, and claims before using this AI-generated draft.")
                            Text(draft.text).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                        }.padding()
                    }.navigationTitle("Application draft").navigationBarTitleDisplayMode(.inline)
                        .toolbar { ShareLink(item: draft.text) }
                } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(model.jobs.first { $0.id == draft.jobId }?.title ?? "Application draft").font(.headline)
                        Text(model.jobs.first { $0.id == draft.jobId }?.company ?? "Saved draft").foregroundStyle(.secondary)
                        Label("Ready for review", systemImage: "checkmark.circle").font(.caption).foregroundStyle(Theme.accent)
                    }.padding(.vertical, 8)
                }
            }
        }.navigationTitle("Drafts").refreshable { await model.reload() }
    }
}
