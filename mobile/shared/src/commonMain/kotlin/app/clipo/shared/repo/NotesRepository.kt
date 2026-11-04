package app.clipo.shared.repo

import app.clipo.shared.api.ApiResult
import app.clipo.shared.api.accountChanged
import app.clipo.shared.api.resultOf
import app.clipo.shared.api.wireJson
import app.clipo.shared.auth.AuthRepository
import app.clipo.shared.db.NoteCache
import app.clipo.shared.model.generated.NoteItem
import app.clipo.shared.model.generated.NotePage
import app.clipo.shared.model.generated.NoteResponse
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

@OptIn(ExperimentalCoroutinesApi::class)
class NotesRepository internal constructor(
    private val auth: AuthRepository,
    private val cache: NoteCache,
) {
    private val refreshMutex = Mutex()
    val notes: Flow<List<NoteItem>> =
        auth.account.flatMapLatest { owner ->
            owner?.let { cache.notes(it.generation) } ?: flowOf(emptyList())
        }

    fun detail(id: Long): Flow<NoteResponse?> =
        auth.account.flatMapLatest { owner ->
            owner?.let { cache.detail(it.generation, id) } ?: flowOf(null)
        }

    suspend fun refresh(loadMore: Boolean = false): ApiResult<Boolean> =
        resultOf {
            refreshMutex.withLock {
                val owner = auth.account.value ?: accountChanged()
                val cursor = if (loadMore) cache.cursor(owner.generation) ?: return@withLock false else null
                val parameters = mutableMapOf("limit" to "50")
                if (cursor != null) parameters["cursor"] = cursor
                val page = wireJson.decodeFromString<NotePage>(auth.authorized(owner, "/notes", parameters))
                cache.savePage(owner.generation, page.items, page.nextCursor, !loadMore)
                page.nextCursor != null
            }
        }

    suspend fun refreshDetail(id: Long): ApiResult<Unit> =
        resultOf {
            val owner = auth.account.value ?: accountChanged()
            val note = wireJson.decodeFromString<NoteResponse>(auth.authorized(owner, "/notes/$id"))
            cache.saveDetail(owner.generation, note)
        }
}
