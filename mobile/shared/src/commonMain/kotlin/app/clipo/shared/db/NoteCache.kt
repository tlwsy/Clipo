package app.clipo.shared.db

import app.cash.sqldelight.coroutines.asFlow
import app.cash.sqldelight.coroutines.mapToList
import app.clipo.shared.api.wireJson
import app.clipo.shared.model.generated.NoteItem
import app.clipo.shared.model.generated.NoteResponse
import app.clipo.shared.model.generated.UserResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString
import kotlin.uuid.ExperimentalUuidApi
import kotlin.uuid.Uuid

internal class NoteCache(
    private val database: ClipoDatabase,
) {
    private val queries = database.cacheQueries

    fun account(): Account? = queries.activeAccount().executeAsOneOrNull()

    @OptIn(ExperimentalUuidApi::class)
    fun accept(
        server: String,
        user: UserResponse,
        version: String,
    ): Account {
        val previous = account()
        if (previous?.server_id == server && previous.user_id == user.id && previous.username == user.username) {
            queries.updateAccount(user.email, version, previous.generation)
            return account()!!
        }
        database.transaction {
            queries.clearAccount()
            queries.saveAccount(server, user.id, user.username, user.email, Uuid.random().toString(), version)
        }
        return account()!!
    }

    fun clear() {
        queries.clearAccount()
    }

    fun notes(generation: String): Flow<List<NoteItem>> =
        queries
            .listNotes(generation)
            .asFlow()
            .mapToList(Dispatchers.Default)
            .map { rows -> rows.map { wireJson.decodeFromString<NoteItem>(it) } }

    fun detail(
        generation: String,
        id: Long,
    ): Flow<NoteResponse?> =
        queries
            .detail(generation, id)
            .asFlow()
            .mapToList(Dispatchers.Default)
            .map { rows -> rows.firstOrNull()?.let { wireJson.decodeFromString<NoteResponse>(it) } }

    fun savePage(
        generation: String,
        items: List<NoteItem>,
        cursor: String?,
        replace: Boolean,
    ) {
        database.transaction {
            if (account()?.generation != generation) return@transaction
            // Keep cached details on a first-page refresh. Full-list reconciliation happens on pagination completion.
            if (replace) queries.saveState(generation, "seen_ids", "")
            val seen =
                queries
                    .state(generation, "seen_ids")
                    .executeAsOneOrNull()
                    .orEmpty()
                    .split(',')
                    .filter { it.isNotEmpty() }
                    .toMutableSet()
            items.forEach {
                queries.saveNote(generation, it.id, it.createdAt, wireJson.encodeToString(it))
                seen.add(it.id.toString())
            }
            queries.saveState(generation, "seen_ids", seen.joinToString(","))
            queries.saveState(generation, "cursor", cursor.orEmpty())
            if (cursor == null) {
                queries.listNotes(generation).executeAsList().forEach { json ->
                    val item = wireJson.decodeFromString<NoteItem>(json)
                    if (item.id.toString() !in seen) queries.removeNote(generation, item.id)
                }
            }
        }
    }

    fun cursor(generation: String): String? = queries.state(generation, "cursor").executeAsOneOrNull()?.ifEmpty { null }

    fun saveDetail(
        generation: String,
        note: NoteResponse,
    ) {
        database.transaction {
            if (account()?.generation != generation) return@transaction
            val item =
                NoteItem(
                    note.id,
                    note.title,
                    note.url,
                    note.source.platform,
                    note.source.siteName,
                    note.source.author,
                    note.summaryMarkdown.orEmpty().take(200),
                    note.status,
                    note.createdAt,
                    note.isFavorite,
                    note.tags,
                )
            queries.saveNote(generation, item.id, item.createdAt, wireJson.encodeToString(item))
            queries.saveDetail(generation, note.id, wireJson.encodeToString(note), note.updatedAt)
        }
    }
}
