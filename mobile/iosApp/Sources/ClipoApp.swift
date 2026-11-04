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
        Group {
            if model.state.screen == .notes {
                TabView {
                    NotesNavigation().tabItem { Label("notes", systemImage: "doc.text") }
                    NavigationStack {
                        Form {
                            Section("server") {
                                Text(model.state.account?.username ?? "")
                                Text(model.state.server)
                                Text(model.state.serverVersion)
                            }
                            Section("reading_style") {
                                Button("global_reading") { model.shared.beginReading(noteScope: false) }
                            }
                            Section { Button("logout", role: .destructive) { confirmLogout = true } }
                        }.navigationTitle("settings").nativeBars()
                    }.tabItem { Label("settings", systemImage: "gearshape") }
                }.nativeBars()
            } else {
                NavigationStack {
                    VStack(spacing: 0) { ConnectionBanner(); LoginView() }.navigationTitle("Clipo").nativeBars()
                }
            }
        }
        .sheet(isPresented: Binding(get: { model.state.readingDraft != nil },
                                    set: { if !$0 { model.shared.cancelReading() } })) {
            ReadingSettingsView().presentationDetents([.large]).interactiveDismissDisabled(model.state.readingSaving)
        }
        .confirmationDialog("logout_title", isPresented: $confirmLogout, titleVisibility: .visible) {
            Button("logout", role: .destructive) { model.shared.logout() }
            Button("cancel", role: .cancel) { }
        } message: { Text("logout_message") }
    }
}

struct ConnectionBanner: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        if model.state.busy { ProgressView().padding(8) }
        if let failure = model.state.failure {
            VStack(spacing: 4) {
                Text(failure.message).foregroundStyle(.red)
                if model.state.screen == .notes { Text("cached_hint").font(.footnote).foregroundStyle(.secondary) }
            }.padding(8)
        }
    }
}

struct NotesNavigation: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var path: [Int64] = []

    var body: some View {
        Group {
            if sizeClass == .regular {
                NavigationSplitView {
                    VStack(spacing: 0) { ConnectionBanner(); NotesView { model.shared.openNote(id: $0) } }
                        .navigationTitle("notes").navigationSplitViewColumnWidth(min: 280, ideal: 320).nativeBars()
                } detail: {
                    if model.state.selectedId != nil { NoteView().nativeBars() }
                    else { ContentUnavailableView("select_note", systemImage: "doc.text") }
                }
            } else {
                NavigationStack(path: $path) {
                    VStack(spacing: 0) {
                        ConnectionBanner()
                        NotesView { noteId in model.shared.openNote(id: noteId); path = [noteId] }
                    }
                    .navigationTitle("notes").nativeBars()
                    .navigationDestination(for: Int64.self) { _ in NoteView().nativeBars() }
                }
                .onChange(of: path) { _, value in if value.isEmpty { model.shared.closeNote() } }
            }
        }
        .onChange(of: sizeClass) { _, value in
            if value != .regular, let noteId = model.state.selectedId { path = [noteId.int64Value] }
        }
    }
}

extension View {
    @ViewBuilder func nativeBars() -> some View {
        if #available(iOS 26, *) { self }
        else { self.toolbarBackground(.ultraThinMaterial, for: .navigationBar, .tabBar) }
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
    let select: (Int64) -> Void
    @EnvironmentObject private var model: AppModel
    var body: some View {
        List {
            if model.state.notes.isEmpty { Text(LocalizedStringKey(model.state.busy ? "loading" : "empty")) }
            ForEach(model.state.notes, id: \.id) { note in
                Button {
                    select(note.id)
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
