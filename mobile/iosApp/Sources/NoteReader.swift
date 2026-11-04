import ClipoShared
import SwiftUI

struct NoteView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if let note = model.state.detail {
                ReaderPage(note: note, style: ReadingStyle.shared.resolve(
                    global: model.state.preferences ?? note.readingPreferences, overrides: note.displayOverrides))
                    .id(note.id)
            } else {
                ContentUnavailableView {
                    Label(LocalizedStringKey(model.state.failure == nil ? "loading" : "not_cached"), systemImage: "doc.text")
                } actions: {
                    Button("retry") {
                        if let noteId = model.state.selectedId { model.shared.openNote(id: noteId.int64Value) }
                    }
                }
            }
        }
        .navigationTitle("original")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { model.shared.beginReading(noteScope: true) } label: { Label("reading_style", systemImage: "textformat.size") }
                    .disabled(model.state.detail == nil)
            }
        }
    }
}

struct ReaderPage: View {
    let note: NoteResponse
    let style: ReadingPreferences
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    private var colors: ReadingColors { ReadingStyle.shared.colors(style: style, systemDark: colorScheme == .dark) }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: CGFloat(style.paragraphSpacing)) {
                Text(note.title).font(.largeTitle.bold()).accessibilityAddTraits(.isHeader)
                Text([note.source.siteName ?? note.source.platform, note.source.author,
                      note.source.publishedAt.map { String($0.prefix(10)) }].compactMap { $0 }.joined(separator: " · "))
                    .font(.caption)
                ReaderLink(title: note.url, target: note.url)
                section("summary")
                if let markdown = note.summaryMarkdown, !markdown.isEmpty {
                    ForEach(ReaderDocument.shared.markdown(source: markdown), id: \.index) { block in
                        BlockView(block: block, style: style, colors: colors)
                    }
                } else { Text("no_summary") }
                ForEach(Array(note.keyPoints.enumerated()), id: \.offset) { _, point in Text("• \(point)") }
                section("original")
                ForEach(ReaderDocument.shared.blocks(content: note.content), id: \.index) { block in
                    BlockView(block: block, style: style, colors: colors)
                }
                ForEach(ReaderDocument.shared.extraImages(content: note.content), id: \.self) { url in
                    ReaderImage(target: url, alt: "")
                }
                if !note.commentInsights.isEmpty { section("comment_insights") }
                ForEach(Array(note.commentInsights.enumerated()), id: \.offset) { _, insight in Text("• \(insight.text)") }
                if note.comments.contains(where: { $0.isValuable }) { section("comments") }
                ForEach(note.comments.filter(\.isValuable), id: \.id) { comment in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(comment.author ?? "").bold()
                        if let score = comment.aiScore { Text(String(format: String(localized: "ai_score"), score.doubleValue)) }
                        Text(comment.content)
                        if let reason = comment.aiReason { Text(reason).italic() }
                    }.padding(.leading, comment.parentSourceId == nil ? 0 : 16)
                }
                if !note.annotations.isEmpty { section("my_annotations") }
                ForEach(note.annotations, id: \.id) { annotation in
                    VStack(alignment: .leading) {
                        Text("“\(annotation.selectedText)”")
                        if let text = annotation.noteText { Text(text) }
                    }
                }
            }
            .font(Font(ReaderText.font(style: style, category: dynamicTypeSize.readingCategory)))
            .textSelection(.enabled)
            .frame(maxWidth: CGFloat(style.contentWidth), alignment: .leading).padding(24)
            .frame(maxWidth: .infinity)
        }
        .foregroundStyle(Color(uiColor: UIColor(readingHex: colors.text)))
        .tint(Color(uiColor: UIColor(readingHex: colors.accent)))
        .background(Color(uiColor: UIColor(readingHex: colors.background)))
    }

    private func section(_ key: LocalizedStringKey) -> some View {
        Text(key).font(.headline).accessibilityAddTraits(.isHeader)
    }
}

struct BlockView: View {
    let block: ReaderBlock
    let style: ReadingPreferences
    let colors: ReadingColors
    @State private var expanded = false

    var body: some View {
        // Type erasure bounds recursive SwiftUI generic expansion; rendering stays native.
        AnyView(content)
    }

    @ViewBuilder private var content: some View {
        switch block.kind {
        case "divider": Divider()
        case "image": ReaderImage(target: block.url, alt: block.alt)
        case "details":
            DisclosureGroup(isExpanded: $expanded) { children } label: {
                Text(block.text.isEmpty ? String(localized: "details") : block.text)
            }
        case "table":
            ScrollView(.horizontal) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(block.children, id: \.index) { row in
                        HStack(alignment: .top, spacing: 0) {
                            ForEach(row.children, id: \.index) { cell in
                                ReaderText(block: cell, style: style, colors: colors).padding(12).frame(width: 180)
                                    .border(Color(uiColor: UIColor(readingHex: colors.text)).opacity(0.25))
                            }
                        }
                    }
                }
            }
        case "code":
            ReaderText(block: block, style: style, colors: colors).padding(12)
                .background(Color(uiColor: UIColor(readingHex: colors.text)).opacity(0.06))
        case "game_card":
            VStack(alignment: .leading, spacing: 8) {
                if let image = block.image { ReaderImage(target: image, alt: block.alt) }
                ReaderLink(title: block.text, target: block.url)
            }.padding(12).border(Color(uiColor: UIColor(readingHex: colors.accent)))
        default:
            VStack(alignment: .leading, spacing: CGFloat(style.paragraphSpacing)) {
                if !block.text.isEmpty { ReaderText(block: block, style: style, colors: colors) }
                children
            }.padding(.leading, block.kind == "quote" ? 16 : 0)
        }
    }

    private var children: some View {
        VStack(alignment: .leading, spacing: CGFloat(style.paragraphSpacing)) {
            ForEach(block.children, id: \.index) { child in BlockView(block: child, style: style, colors: colors) }
        }.padding(.leading, block.kind == "list_item" ? 16 : 0)
    }
}

struct ReaderLink: View {
    let title: String
    let target: String?
    var body: some View {
        if let safe = ReaderDocument.shared.safeUrl(value: target), let url = URL(string: safe) {
            Link(title, destination: url)
        } else { Text(title) }
    }
}

struct ReaderImage: View {
    let target: String?
    let alt: String
    @State private var retry = 0
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let safe = ReaderDocument.shared.safeUrl(value: target), let url = URL(string: safe) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image): image.resizable().scaledToFit().frame(maxHeight: 420).accessibilityLabel(alt)
                    case .failure:
                        Text("image_unavailable")
                        Button("retry") { retry += 1 }
                    default: ProgressView().frame(minHeight: 96)
                    }
                }.id(retry)
                Link("open_image", destination: url)
            } else { Text("image_unavailable") }
            if !alt.isEmpty { Text(alt).font(.caption) }
        }
    }
}
