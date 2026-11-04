import ClipoShared
import SwiftUI

struct ReadingSettingsView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var invalidColors: Set<String> = []

    var body: some View {
        NavigationStack {
            if let draft = model.state.readingDraft {
                Form {
                    Section {
                        Picker("reading_style", selection: Binding(get: { model.state.readingNoteId != nil },
                                                                  set: { model.shared.beginReading(noteScope: $0) })) {
                            Text("global_scope").tag(false)
                            if model.state.detail != nil { Text("note_scope").tag(true) }
                        }.pickerStyle(.segmented)
                        preview(draft)
                        if let failure = model.state.readingFailure { Text(failure.message).foregroundStyle(.red) }
                    }
                    Section("theme") {
                        choices("theme", key: "theme", value: draft.theme,
                                options: ["comfortable", "compact", "focus", "print"],
                                labels: ["comfortable", "compact", "focus", "print_theme"])
                    }
                    colorSection(draft)
                    fontSection(draft)
                    Section {
                        if model.state.readingNoteId != nil {
                            Button("reset_note_style", role: .destructive) { model.shared.saveReading(reset: true) }
                        }
                        Text("style_online_hint").font(.footnote)
                    }
                }
                .disabled(model.state.readingSaving)
                .navigationTitle("reading_style").navigationBarTitleDisplayMode(.inline).nativeBars()
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("cancel") { model.shared.cancelReading() }.disabled(model.state.readingSaving)
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        if model.state.readingSaving { ProgressView() } else { Button("save") { model.shared.saveReading(reset: false) }.disabled(!invalidColors.isEmpty) }
                    }
                }
                .onChange(of: draft.theme) { _, _ in invalidColors = [] }
                .onChange(of: draft.colorMode) { _, _ in invalidColors = [] }
                .onChange(of: model.state.readingNoteId) { _, _ in invalidColors = [] }
            }
        }
    }

    private func colorSection(_ draft: ReadingPreferences) -> some View {
        Section("color_mode") {
            choices("color_mode", key: "color_mode", value: draft.colorMode,
                    options: ["custom", "system", "monet"], labels: ["custom_colors", "system_colors", "monet_colors"])
            if draft.colorMode == "custom" {
                color("background_color", key: "background_color", value: draft.backgroundColor)
                color("text_color", key: "text_color", value: draft.textColor)
            }
            if draft.colorMode == "monet" {
                color("seed_color", key: "monet_seed", value: draft.monetSeed)
                choices("monet_scheme", key: "monet_scheme", value: draft.monetScheme,
                        options: ["system", "light", "dark"], labels: ["system_colors", "light", "dark"])
            }
        }
    }

    private func fontSection(_ draft: ReadingPreferences) -> some View {
        Section("font") {
            choices("font", key: "font_family", value: draft.fontFamily,
                    options: ["system-ui", "serif", "sans-serif", "online"],
                    labels: ["font_system", "font_serif", "font_sans", "font_bundled"])
            Text("font_hint").font(.footnote)
            choices("weight", key: "font_weight", value: String(draft.fontWeight),
                    options: ["400", "500", "600", "700"], labels: ["weight_400", "weight_500", "weight_600", "weight_700"])
            number("font_size", key: "font_size", value: Double(draft.fontSize), range: 14...24, step: 1)
            number("line_height", key: "line_height", value: draft.lineHeight, range: 1.2...2, step: 0.1)
            number("paragraph_spacing", key: "paragraph_spacing", value: Double(draft.paragraphSpacing), range: 0...40, step: 1)
            number("content_width", key: "content_width", value: Double(draft.contentWidth), range: 600...900, step: 10)
            choices("alignment", key: "text_align", value: draft.textAlign,
                    options: ["left", "justify"], labels: ["align_left", "align_justify"])
        }
    }

    private func preview(_ style: ReadingPreferences) -> some View {
        let colors = ReadingStyle.shared.colors(style: style, systemDark: colorScheme == .dark)
        return Text("style_preview").font(Font(ReaderText.font(style: style, category: dynamicTypeSize.readingCategory)))
            .foregroundStyle(Color(uiColor: UIColor(readingHex: colors.text)))
            .frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .background(Color(uiColor: UIColor(readingHex: colors.background)))
    }

    private func choices(_ label: LocalizedStringKey, key: String, value: String,
                         options: [String], labels: [String]) -> some View {
        Picker(label, selection: Binding(get: { value }, set: { model.shared.editReading(key: key, value: $0) })) {
            ForEach(Array(options.enumerated()), id: \.element) { index, option in
                Text(LocalizedStringKey(labels[index])).tag(option)
            }
        }
    }

    private func number(_ label: LocalizedStringKey, key: String, value: Double,
                        range: ClosedRange<Double>, step: Double) -> some View {
        VStack(alignment: .leading) {
            HStack { Text(label); Spacer(); Text(value, format: .number.precision(.fractionLength(0...1))) }
            Slider(value: Binding(get: { value }, set: {
                model.shared.editReading(key: key, value: key == "line_height" ? String(($0 * 10).rounded() / 10) : String(Int($0.rounded())))
            }), in: range, step: step).accessibilityLabel(Text(label))
        }
    }

    private func color(_ label: LocalizedStringKey, key: String, value: String) -> some View {
        ReadingColorField(label: label, value: value) { text, valid in
            if valid { invalidColors.remove(key); model.shared.editReading(key: key, value: text) } else { invalidColors.insert(key) }
        }.id("\(key)-\(model.state.readingNoteId?.stringValue ?? "global")-\(model.state.readingDraft?.theme ?? "")")
    }
}

private struct ReadingColorField: View {
    let label: LocalizedStringKey
    let value: String
    let change: (String, Bool) -> Void
    @State private var draft = ""
    private var valid: Bool { draft.range(of: "^#[0-9a-fA-F]{6}$", options: .regularExpression) != nil }
    var body: some View {
        VStack(alignment: .leading) {
            TextField(label, text: $draft).textInputAutocapitalization(.never).autocorrectionDisabled()
                .onChange(of: draft) { _, value in change(value, valid) }
            if !valid { Text("color_hint").font(.footnote).foregroundStyle(.red) }
        }
        .onAppear { draft = value }
        .onChange(of: value) { _, value in draft = value }
    }
}
