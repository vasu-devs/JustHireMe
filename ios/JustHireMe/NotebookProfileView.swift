import SwiftUI
import PDFKit
import UniformTypeIdentifiers

struct NotebookProfileView: View {
    @Environment(NotebookModel.self) private var book
    @State private var importPresented = false
    @State private var editingIdentity = false
    @State private var editing: NotebookSection?
    @State private var message: String?

    var body: some View {
        @Bindable var book = book
        NotebookPage {
            NotebookHeading(chapter: "01 / Profile", title: "Your profile", subtitle: "Your experience, work and skills. Edit any section below.")
            if book.isConnected { ConnectedProfileControls() }
            identity
            NotebookCard(tint: NotebookInk.sky) {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(alignment: .top) {
                        Image(systemName: "doc.badge.plus").font(.system(size: 30, weight: .light))
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Add to your profile").font(Theme.heading(20))
                            Text("Résumé, portfolio notes, Markdown, or other files.").font(Theme.sans(13)).foregroundStyle(Theme.copy)
                        }
                    }
                    NotebookButton(title: "Add files or notes", symbol: "plus") { importPresented = true }
                        .accessibilityIdentifier("notebook.import")
                    HStack {
                        Text("\(book.sources.count) source\(book.sources.count == 1 ? "" : "s")").font(Theme.sans(12))
                        Spacer()
                        Text("\(book.profile.completedSections) of 6 sections filled").font(Theme.sans(11))
                    }.foregroundStyle(Theme.copy)
                }
            }
            HStack { Text("Profile details").font(Theme.heading(21)); Spacer(); Image(systemName: "pencil").foregroundStyle(Theme.accent) }
            ForEach(Array(NotebookSection.allCases.enumerated()), id: \.element) { index, section in
                sectionCard(section, index: index)
            }
            if !book.sources.isEmpty {
                NotebookCard {
                    VStack(alignment: .leading, spacing: 13) {
                        Text("Source files").font(Theme.heading(18))
                        ForEach(book.sources) { source in
                            HStack {
                                Image(systemName: source.pending ? "clock" : "doc.text")
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(source.filename).font(Theme.sans(13, bold: true))
                                    Text(source.pending ? "Waiting for connected processing" : "Added to your notebook").font(Theme.sans(11)).foregroundStyle(Theme.copy)
                                }
                                Spacer()
                            }
                        }
                    }
                }
            }
            if let message { InlineMessage(text: message) }
            ShareLink(item: exportText) { Label("Export profile", systemImage: "square.and.arrow.up").font(Theme.sans(13, bold: true)) }
            Text(book.isConnected ? "Profile sections sync when you save. Source attachments stay in this session; keep your originals." : "Changes stay in this session. Export a copy to keep them; account sync is not connected yet.").font(Theme.sans(11)).foregroundStyle(Theme.copy)
        }.navigationTitle("My notebook")
            .disabled(book.isBusy)
            .sheet(isPresented: $importPresented) { ProfileImportView() }
    }

    private var identity: some View {
        @Bindable var book = book
        return NotebookCard(ruled: true) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top) {
                    Text(book.profile.name.isEmpty ? "?" : book.profile.name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined())
                        .font(Theme.display(28)).frame(width: 60, height: 66).background(NotebookInk.lavender)
                        .rotationEffect(.degrees(-4)).overlay(PencilOutline().stroke(Theme.ink.opacity(0.2), lineWidth: 1).rotationEffect(.degrees(-4)))
                    VStack(alignment: .leading, spacing: 6) {
                        Text(book.profile.name.isEmpty ? "Add your name" : book.profile.name).font(Theme.heading(20))
                        Text(book.profile.headline.isEmpty ? "Add your role or a short introduction." : book.profile.headline).font(Theme.sans(13)).foregroundStyle(Theme.copy)
                    }
                    Spacer(minLength: 0)
                    Button(editingIdentity ? "Done" : "Edit") { editingIdentity.toggle() }
                        .font(Theme.sans(12, bold: true)).accessibilityIdentifier("notebook.identity.edit")
                }
                if editingIdentity {
                    TextField("Full name", text: $book.profile.name).accessibilityIdentifier("notebook.name")
                    TextField("Headline", text: $book.profile.headline)
                    TextField("Portfolio URL", text: $book.profile.portfolio).keyboardType(.URL).textInputAutocapitalization(.never)
                    TextField("Target roles, separated by commas", text: $book.profile.targetRoles, axis: .vertical)
                    TextField("Preferred location", text: $book.profile.location)
                } else {
                    if !book.profile.portfolio.isEmpty { Label(book.profile.portfolio, systemImage: "link").font(Theme.sans(12)).foregroundStyle(Theme.accent).textSelection(.enabled) }
                    Label(book.profile.targetRoles, systemImage: "bookmark").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                    Label(book.profile.location, systemImage: "mappin").font(Theme.sans(12)).foregroundStyle(Theme.copy)
                }
            }
        }
    }

    private func sectionCard(_ section: NotebookSection, index: Int) -> some View {
        NotebookCard(ruled: true) {
            VStack(alignment: .leading, spacing: 15) {
                HStack {
                    Image(systemName: section.symbol).frame(width: 35, height: 35).background(NotebookInk.color(index), in: RoundedRectangle(cornerRadius: 7)).rotationEffect(.degrees(-3))
                    Text(section.title).font(Theme.heading(19))
                    Spacer()
                    Button(editing == section ? "Done" : "Edit") { editing = editing == section ? nil : section }
                        .font(Theme.sans(12, bold: true)).accessibilityIdentifier("section.edit.\(section.id)")
                }
                if editing == section {
                    TextEditor(text: Binding(get: { book.profile[section] }, set: { book.profile[section] = $0 }))
                        .frame(minHeight: 145).scrollContentBackground(.hidden).font(Theme.sans(14))
                        .accessibilityLabel(section.title).accessibilityIdentifier("section.editor.\(section.id)")
                } else {
                    Text(book.profile[section].isEmpty ? "Add your \(section.title.lowercased())." : book.profile[section])
                        .font(Theme.sans(14)).foregroundStyle(Theme.copy).lineSpacing(5).textSelection(.enabled)
                }
            }
        }
    }
    private var exportText: String {
        "# \(book.profile.name)\n\(book.profile.headline)\n\(book.profile.portfolio)\n\n" + NotebookSection.allCases.map { "## \($0.title)\n\(book.profile[$0])" }.joined(separator: "\n\n")
    }
}

struct ProfileImportView: View {
    @Environment(NotebookModel.self) private var book
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var picker = false
    @State private var proposal: ProfileImport?
    @State private var error: String?
    @State private var busy = false
    @FocusState private var notesFocused: Bool
    var body: some View {
        NavigationStack {
            NotebookPage {
                NotebookHeading(chapter: "Profile / Import", title: "Add your content", subtitle: "Add a file or paste your notes. Review the sections, then add them to your profile.", tint: NotebookInk.sky)
                NotebookButton(title: busy ? "Reading your file…" : "Choose a file", symbol: "arrow.up.doc") { picker = true }
                    .disabled(busy).accessibilityIdentifier("import.file")
                Text("Markdown, text & readable PDFs organize locally. Other formats can be attached for future connected processing. Up to 10 MB per file.")
                    .font(Theme.sans(12)).foregroundStyle(Theme.copy)
                NotebookCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Paste your notes").font(Theme.heading(18))
                        TextEditor(text: $text).frame(minHeight: 155).scrollContentBackground(.hidden)
                            .focused($notesFocused)
                            .accessibilityLabel("Profile notes").accessibilityIdentifier("import.notes")
                        Button("Organize my notes") { proposal = ProfileTextParser.parse(text, filename: "Pasted notes"); error = nil }
                            .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty).accessibilityIdentifier("import.organize")
                        if book.isPreview {
                            Button("Try a Markdown example") { text = NotebookSamples.importText; proposal = ProfileTextParser.parse(text, filename: "My-portfolio.md") }
                                .font(Theme.sans(12)).accessibilityIdentifier("import.example")
                        }
                    }
                }
                if let proposal {
                    NotebookCard(tint: NotebookInk.mint) {
                        VStack(alignment: .leading, spacing: 14) {
                            Text(proposal.filename).font(Theme.heading(18))
                            Text(proposal.summary).font(Theme.sans(13)).accessibilityIdentifier("import.summary")
                            ForEach(NotebookSection.allCases.filter { proposal.sections[$0.rawValue] != nil }) { section in
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(section.title).font(Theme.sans(13, bold: true))
                                    Text(proposal.sections[section.rawValue] ?? "").font(Theme.sans(12)).foregroundStyle(Theme.copy).lineLimit(4)
                                }
                            }
                            if proposal.pending { Text("No content was extracted. This attachment stays in this session; it has not been uploaded.").font(Theme.sans(12)) }
                            NotebookButton(title: proposal.pending ? "Keep attachment for this session" : "Add to my profile", symbol: "checkmark") {
                                do { try book.add(proposal); dismiss() } catch { self.error = error.localizedDescription }
                            }.accessibilityIdentifier("import.accept")
                        }
                    }
                }
                if let error { InlineMessage(text: error) }
            }.navigationTitle("Add content")
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
                .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { notesFocused = false }.accessibilityIdentifier("import.dismiss-keyboard") } }
                .fileImporter(isPresented: $picker, allowedContentTypes: [.item]) { result in
                    switch result { case .success(let url): Task { await read(url) }; case .failure(let error): self.error = error.localizedDescription }
                }
        }
    }
    private func read(_ url: URL) async {
        busy = true; error = nil
        defer { busy = false }
        do {
            guard book.sources.count < 8 else { throw AppError.message("Keep up to 8 source files in this preview session.") }
            let value = try await Task.detached(priority: .userInitiated) {
                let granted = url.startAccessingSecurityScopedResource()
                defer { if granted { url.stopAccessingSecurityScopedResource() } }
                let size = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
                guard size.isRegularFile == true, (size.fileSize ?? Int.max) <= 10 * 1024 * 1024 else { throw AppError.message("Choose a regular file smaller than 10 MB.") }
                let data = try Data(contentsOf: url)
                let ext = url.pathExtension.lowercased()
                var extracted: String?
                if ext == "pdf" { extracted = PDFDocument(data: data)?.string }
                else if ["md", "markdown", "txt", "csv", "json"].contains(ext) { extracted = String(data: data, encoding: .utf8) }
                if let extracted, !extracted.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    return ProfileTextParser.parse(extracted, filename: url.lastPathComponent)
                }
                return ProfileImport(filename: url.lastPathComponent, sections: [:], pending: true, payload: data)
            }.value
            proposal = value
        } catch { self.error = error.localizedDescription }
    }
}
