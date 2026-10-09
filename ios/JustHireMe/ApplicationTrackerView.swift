import SwiftUI
import Charts

struct ApplicationTrackerView: View {
    @Environment(NotebookModel.self) private var book
    @State private var filter: ApplicationStage?
    private var visible: [ApplicationRecord] { book.applications.filter { filter == nil || $0.stage == filter } }
    private var stages: [ApplicationStage] { ApplicationStage.allCases.filter { count($0) > 0 } }
    private func count(_ stage: ApplicationStage) -> Int {
        guard let summary = book.summary, book.isConnected else { return book.applications.filter { $0.stage == stage }.count }
        switch stage {
        case .interviewing: return summary.employerOutcomes["interview", default: 0]
        case .offer, .rejected, .withdrawn: return summary.employerOutcomes[stage.rawValue, default: 0]
        case .submitted: return max(0, summary.applications["submitted", default: 0] - ["interview", "offer", "rejected", "withdrawn"].reduce(0) { $0 + summary.employerOutcomes[$1, default: 0] })
        case .needsAttention: return summary.applications["needs_user", default: 0]
        default: return summary.applications[stage.rawValue, default: 0]
        }
    }
    var body: some View {
        NotebookPage {
            NotebookHeading(chapter: "03 / Tracker", title: "Your applications", subtitle: "Track responses, interviews and offers.", tint: NotebookInk.peach)
            NotebookCard(ruled: true) {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(alignment: .firstTextBaseline) {
                        Text("\(book.summary?.total ?? book.applications.count)").font(Theme.sans(32, bold: true))
                        Text("applications total").font(Theme.sans(13)).foregroundStyle(Theme.copy)
                    }
                    if book.applications.isEmpty {
                        Text("Your first application will start the chart.").font(Theme.sans(14)).foregroundStyle(Theme.copy)
                    } else {
                        Chart(Array(stages.enumerated()), id: \.element.id) { index, stage in
                            BarMark(x: .value("Applications", count(stage)), y: .value("Status", stage.title))
                                .foregroundStyle(NotebookInk.color(index)).cornerRadius(4)
                        }.chartXScale(domain: 0...max(1, book.summary?.total ?? book.applications.count)).frame(height: CGFloat(max(3, stages.count) * 35))
                            .accessibilityLabel("Application outcomes")
                            .accessibilityValue(stages.map { stage in "\(stage.title): \(count(stage))" }.joined(separator: ", "))
                    }
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    filterButton(nil)
                    ForEach(ApplicationStage.allCases) { filterButton($0) }
                }
            }
            if visible.isEmpty {
                Text("No applications yet.").font(Theme.display(25)).padding(.vertical, 16)
            }
            ForEach(visible) { record in
                NavigationLink { ApplicationRecordView(record: record) } label: {
                    NotebookCard(tint: tint(record.stage)) {
                        VStack(alignment: .leading, spacing: 13) {
                            HStack {
                                Label(record.stage.title, systemImage: record.stage.symbol).font(Theme.sans(11, bold: true))
                                Spacer()
                                Text(record.date, format: .dateTime.month(.abbreviated).day()).font(Theme.mono(10))
                            }
                            Text(record.role.title).font(Theme.heading(21))
                            HStack { Text(record.role.company).font(Theme.sans(13)); Spacer(); Image(systemName: "arrow.up.right") }
                        }
                    }
                }.buttonStyle(.plain).accessibilityIdentifier("application.\(record.role.id)")
            }
            if book.nextActivityOffset != nil { Button("Load more applications") { Task { do { try await book.loadMoreActivity() } catch { book.connectionMessage = error.localizedDescription } } } }
            if let message = book.connectionMessage { InlineMessage(text: message) }
        }.navigationTitle("Applications")
            .refreshable { do { try await book.refreshConnection() } catch { book.connectionMessage = error.localizedDescription } }
    }
    private func filterButton(_ stage: ApplicationStage?) -> some View {
        Button { filter = stage } label: {
            Text(stage?.title ?? "All").font(Theme.sans(12, bold: true)).padding(.horizontal, 14).padding(.vertical, 11)
                .background(filter == stage ? NotebookInk.lavender : Theme.card, in: RoundedRectangle(cornerRadius: 8))
                .foregroundStyle(Theme.ink)
        }.accessibilityIdentifier("tracking.filter.\(stage?.id ?? "all")")
            .accessibilityAddTraits(filter == stage ? .isSelected : [])
    }
    private func tint(_ stage: ApplicationStage) -> Color {
        switch stage { case .submitted: NotebookInk.sky; case .interviewing: NotebookInk.lavender; case .offer: NotebookInk.mint; case .rejected, .failed: NotebookInk.peach; default: NotebookInk.butter }
    }
}

struct ApplicationRecordView: View {
    @Environment(NotebookModel.self) private var book
    let record: ApplicationRecord
    @State private var refreshMessage: String?
    private var current: ApplicationRecord { book.applications.first { $0.id == record.id } ?? record }
    var body: some View {
        NotebookPage {
            NotebookHeading(chapter: "Application details", title: current.role.title, subtitle: current.role.company, tint: NotebookInk.mint)
            NotebookCard(tint: NotebookInk.mint) {
                VStack(alignment: .leading, spacing: 12) {
                    Label(current.stage.title, systemImage: current.stage.symbol).font(Theme.heading(24)).accessibilityIdentifier("application.status")
                    Text(book.isPreview ? "This is a simulated application. Nothing has been sent to the employer." : "The latest confirmed status from the application service.").font(Theme.sans(13)).foregroundStyle(Theme.copy)
                    Text(current.automatic ? (book.isPreview ? "Via auto-apply preview" : "Via auto-apply") : "Requested by you").font(Theme.mono(10))
                }
            }
            NotebookCard(ruled: true) {
                VStack(alignment: .leading, spacing: 21) {
                    Text("Activity").font(Theme.heading(20))
                    ForEach(Array(current.events.enumerated()), id: \.offset) { index, event in
                        HStack(alignment: .top, spacing: 14) {
                            Text(String(index + 1)).font(Theme.mono(11)).frame(width: 26, height: 26).background(NotebookInk.lavender, in: Circle())
                            Text(event).font(Theme.sans(14)).foregroundStyle(Theme.copy)
                        }
                    }
                }
            }
            if book.isConnected { ConnectedApplicationActions(record: current) }
            if let refreshMessage { InlineMessage(text: refreshMessage) }
            if current.stage == .rejected {
                NotebookCard(tint: NotebookInk.peach) {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("No feedback provided").font(Theme.heading(19))
                        Text("The employer hasn’t shared a reason. You can review the skills requested by other roles in Grow.").font(Theme.sans(13))
                        NavigationLink("View learning suggestions") { GrowthView() }
                    }
                }
            }
            if book.isPreview {
                Menu {
                    ForEach(ApplicationStage.allCases) { stage in
                        Button(stage.title) { book.update(current, stage: stage) }.accessibilityIdentifier("outcome.\(stage.id)")
                    }
                } label: { Label("Preview an employer response", systemImage: "arrow.triangle.2.circlepath").font(Theme.sans(13, bold: true)) }
                    .accessibilityIdentifier("application.response")
            }
        }.navigationTitle("Application")
            .task {
                guard book.isConnected else { return }
                while !Task.isCancelled {
                    do {
                        try await book.refreshApplication(record.id)
                        refreshMessage = nil
                        try await Task.sleep(for: .seconds(5))
                    } catch is CancellationError { return }
                    catch { refreshMessage = error.localizedDescription; return }
                }
            }
            .refreshable { do { try await book.refreshApplication(record.id); refreshMessage = nil } catch { refreshMessage = error.localizedDescription } }
    }
}
