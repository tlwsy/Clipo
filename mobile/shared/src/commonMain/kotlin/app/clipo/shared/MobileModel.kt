package app.clipo.shared

import app.clipo.shared.api.ApiResult
import app.clipo.shared.api.Failure
import app.clipo.shared.api.ServerAddress
import app.clipo.shared.auth.AccountInfo
import app.clipo.shared.model.generated.NoteItem
import app.clipo.shared.model.generated.NoteResponse
import app.clipo.shared.model.generated.ReadingPreferences
import app.clipo.shared.reading.ReadingStyle
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class Screen { SERVER, LOGIN, NOTES }

data class MobileState(
    val screen: Screen = Screen.SERVER,
    val server: String = "",
    val serverVersion: String = "",
    val account: AccountInfo? = null,
    val notes: List<NoteItem> = emptyList(),
    val detail: NoteResponse? = null,
    val selectedId: Long? = null,
    val preferences: ReadingPreferences? = null,
    val readingDraft: ReadingPreferences? = null,
    val readingNoteId: Long? = null,
    val readingFailure: Failure? = null,
    val readingSaving: Boolean = false,
    val busy: Boolean = false,
    val hasMore: Boolean = true,
    val failure: Failure? = null,
)

class Observation internal constructor(
    private val job: Job,
) {
    fun close() {
        job.cancel()
    }
}

interface StateObserver {
    fun onState(state: MobileState)
}

/** A platform-independent state holder. Views never access HTTP or tokens. */
class MobileModel(
    private val client: ClipoClient,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val mutable = MutableStateFlow(MobileState())
    val state = mutable.asStateFlow()
    private var detailJob: Job? = null
    private var actionJob: Job? = null
    private var readingJob: Job? = null

    init {
        scope.launch {
            client.auth.account.collectLatest { owner ->
                detailJob?.cancel()
                readingJob?.cancel()
                mutable.value =
                    MobileState(
                        screen = if (owner == null) Screen.SERVER else Screen.NOTES,
                        server = owner?.server.orEmpty(),
                        serverVersion = owner?.serverVersion.orEmpty(),
                        account = owner,
                    )
                if (owner != null) {
                    launch { refresh() }
                    launch { client.notes.refreshPreferences() }
                    launch {
                        client.notes.preferences.collect { style ->
                            mutable.update { it.copy(preferences = style) }
                        }
                    }
                    client.notes.notes.collect { notes -> mutable.update { it.copy(notes = notes) } }
                }
            }
        }
        scope.launch {
            client.auth.needsLogin.collect { required ->
                if (required) {
                    mutable.update {
                        it.copy(screen = Screen.LOGIN, detail = null, selectedId = null, readingDraft = null)
                    }
                }
            }
        }
    }

    fun observe(observer: StateObserver): Observation = Observation(scope.launch { state.collect(observer::onState) })

    fun snapshot(): MobileState = state.value

    fun inspectServer(value: String) =
        action {
            when (val result = client.auth.inspectServer(value)) {
                is ApiResult.Error -> show(result.failure)
                is ApiResult.Success ->
                    mutable.update {
                        if (!result.value.setupCompleted) {
                            it.copy(
                                failure =
                                    app.clipo.shared.api.Failure(
                                        app.clipo.shared.api.FailureKind.PERMANENT,
                                        "setup_required",
                                        "请先在网页完成服务器初始化",
                                    ),
                            )
                        } else {
                            it.copy(
                                screen = Screen.LOGIN,
                                server = ServerAddress.parse(value).baseUrl,
                                serverVersion = result.value.version,
                            )
                        }
                    }
            }
        }

    fun login(
        username: String,
        password: String,
    ) = action {
        val previous = client.auth.account.value
        when (val result = client.auth.login(state.value.server, username, password)) {
            is ApiResult.Error -> show(result.failure)
            is ApiResult.Success -> {
                mutable.update { it.copy(screen = Screen.NOTES, account = result.value) }
                if (result.value == previous) refresh()
            }
        }
    }

    fun refreshNotes(loadMore: Boolean = false) = action { refresh(loadMore) }

    private suspend fun refresh(loadMore: Boolean = false) {
        when (val result = client.notes.refresh(loadMore)) {
            is ApiResult.Error -> show(result.failure)
            is ApiResult.Success -> mutable.update { it.copy(hasMore = result.value, failure = null) }
        }
    }

    fun openNote(id: Long) {
        detailJob?.cancel()
        mutable.update { it.copy(selectedId = id, detail = null, failure = null) }
        detailJob =
            scope.launch {
                launch {
                    when (val result = client.notes.refreshDetail(id)) {
                        is ApiResult.Error -> show(result.failure)
                        is ApiResult.Success -> Unit
                    }
                }
                client.notes.detail(id).collect { note -> mutable.update { it.copy(detail = note) } }
            }
    }

    fun closeNote() {
        detailJob?.cancel()
        mutable.update { it.copy(selectedId = null, detail = null, failure = null) }
    }

    fun beginReading(noteScope: Boolean) {
        if (state.value.readingSaving) return
        val note = state.value.detail
        val global = state.value.preferences ?: note?.readingPreferences
        mutable.update {
            it.copy(
                readingDraft =
                    if (noteScope) {
                        ReadingStyle.resolve(global, note?.displayOverrides)
                    } else {
                        global ?: ReadingStyle.preset("comfortable")
                    },
                readingNoteId = if (noteScope) note?.id else null,
                readingFailure = null,
            )
        }
    }

    fun editReading(
        key: String,
        value: String,
    ) {
        if (state.value.readingSaving) return
        mutable.update { current ->
            val draft = current.readingDraft ?: return@update current
            current.copy(readingDraft = ReadingStyle.edit(draft, key, value) ?: draft, readingFailure = null)
        }
    }

    fun cancelReading() {
        if (!state.value.readingSaving) mutable.update { it.copy(readingDraft = null, readingFailure = null) }
    }

    fun saveReading(reset: Boolean = false) {
        if (readingJob?.isActive == true) return
        val draft = state.value.readingDraft ?: return
        val id = state.value.readingNoteId
        val owner = state.value.account ?: return
        readingJob =
            scope.launch {
                mutable.update { it.copy(readingSaving = true, readingFailure = null) }
                try {
                    val result =
                        if (reset &&
                            id != null
                        ) {
                            client.notes.resetDisplay(id)
                        } else {
                            client.notes.saveStyle(draft, id)
                        }
                    if (state.value.account != owner) return@launch
                    when (result) {
                        is ApiResult.Error -> mutable.update { it.copy(readingFailure = result.failure) }
                        is ApiResult.Success -> mutable.update { it.copy(readingDraft = null) }
                    }
                } finally {
                    if (state.value.account == owner) mutable.update { it.copy(readingSaving = false) }
                }
            }
    }

    fun logout() =
        action {
            detailJob?.cancel()
            when (val result = client.auth.logout()) {
                is ApiResult.Error -> show(result.failure)
                is ApiResult.Success -> Unit
            }
        }

    fun editServer() {
        if (state.value.account == null) mutable.update { it.copy(screen = Screen.SERVER, failure = null) }
    }

    private fun action(block: suspend () -> Unit) {
        if (actionJob?.isActive == true) return
        actionJob =
            scope.launch {
                mutable.update { it.copy(busy = true, failure = null) }
                try {
                    block()
                } finally {
                    mutable.update { it.copy(busy = false) }
                }
            }
    }

    private fun show(failure: Failure) {
        mutable.update { it.copy(failure = failure) }
    }

    fun close() {
        scope.cancel()
        client.close()
    }
}
