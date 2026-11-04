import ClipoShared
import SwiftUI

@MainActor
final class AppModel: NSObject, ObservableObject, StateObserver {
    let shared: MobileModel
    @Published var state: MobileState
    private var observation: Observation?

    override init() {
        shared = MobileModel(client: IosClientKt.createIosClient(tokenStore: KeychainTokenStore()))
        state = shared.snapshot()
        super.init()
        observation = shared.observe(observer: self)
    }

    func onState(state: MobileState) {
        self.state = state
    }
}

@main
struct ClipoApp: App {
    @StateObject private var model = AppModel()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(model) }
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel
    @State private var confirmLogout = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if model.state.busy { ProgressView().padding() }
                if let failure = model.state.failure {
                    Text(failure.message).foregroundStyle(.red).padding()
                    if model.state.screen == .notes {
                        Text("cached_hint").font(.footnote).foregroundStyle(.secondary)
                    }
                }
                if model.state.screen == .notes {
                    if model.state.selectedId != nil { NoteView() } else { NotesView() }
                } else {
                    LoginView()
                }
            }
            .navigationTitle(model.state.screen == .notes ? String(localized: "notes") : "Clipo")
            .toolbar {
                if model.state.selectedId != nil {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("back") { model.shared.closeNote() }
                    }
                }
                if model.state.account != nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("logout", role: .destructive) { confirmLogout = true }
                    }
                }
            }
            .confirmationDialog("logout_title", isPresented: $confirmLogout, titleVisibility: .visible) {
                Button("logout", role: .destructive) { model.shared.logout() }
                Button("cancel", role: .cancel) { }
            } message: {
                Text("logout_message")
            }
        }
    }
}

struct LoginView: View {
    @EnvironmentObject private var model: AppModel
    @State private var server = ""
    @State private var username = ""
    @State private var password = ""

    var body: some View {
        Form {
            if model.state.screen == .server {
                Section("server_title") {
                    TextField("server", text: $server)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Button("continue_action") { model.shared.inspectServer(value: server) }
                        .disabled(server.isEmpty || model.state.busy)
                }
            } else {
                Section("server") {
                    Text(model.state.server)
                    Text(model.state.serverVersion).foregroundStyle(.secondary)
                    if model.state.server.hasPrefix("http:") { Text("http_hint").font(.footnote) }
                }
                Section("login") {
                    TextField("username", text: $username)
                        .textContentType(.username).textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("password", text: $password).textContentType(.password)
                    Button("login") {
                        model.shared.login(username: username, password: password)
                        password = ""
                    }.disabled(username.isEmpty || password.isEmpty || model.state.busy)
                    if model.state.account == nil {
                        Button("change_server") { model.shared.editServer() }
                    }
                }
            }
        }
        .onAppear { server = model.state.server }
    }
}

struct NotesView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        List {
            if model.state.notes.isEmpty { Text(LocalizedStringKey(model.state.busy ? "loading" : "empty")) }
            ForEach(model.state.notes, id: \.id) { note in
                Button {
                    model.shared.openNote(id: note.id)
                } label: {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(note.title).font(.headline).foregroundStyle(.primary)
                        Text(note.siteName ?? note.platform).font(.caption).foregroundStyle(.secondary)
                        Text(note.summaryExcerpt).font(.subheadline).foregroundStyle(.secondary).lineLimit(3)
                    }.padding(.vertical, 8)
                }
            }
            if model.state.hasMore && !model.state.notes.isEmpty {
                Button("load_more") { model.shared.refreshNotes(loadMore: true) }.disabled(model.state.busy)
            }
        }
        .refreshable { model.shared.refreshNotes(loadMore: false) }
        .toolbar {
            ToolbarItem(placement: .bottomBar) {
                Button("refresh") { model.shared.refreshNotes(loadMore: false) }.disabled(model.state.busy)
            }
        }
    }
}

struct NoteView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        if let note = model.state.detail {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 20) {
                    Text(note.title).font(.largeTitle).bold()
                    Text(note.url).font(.caption).foregroundStyle(.secondary)
                    Text("summary").font(.headline)
                    Text(note.summaryMarkdown ?? String(localized: "no_summary"))
                    ForEach(Array(note.keyPoints.enumerated()), id: \.offset) { _, point in Text("• \(point)") }
                    Text("original").font(.headline)
                    ForEach(Array(note.content.text.components(separatedBy: "\n\n").enumerated()), id: \.offset) { _, text in
                        Text(text)
                    }
                }.textSelection(.enabled).frame(maxWidth: 900, alignment: .leading).padding(24)
            }
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
}
