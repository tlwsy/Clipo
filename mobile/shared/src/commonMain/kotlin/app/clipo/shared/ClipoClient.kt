package app.clipo.shared

import app.cash.sqldelight.db.SqlDriver
import app.clipo.shared.api.ClipoApi
import app.clipo.shared.auth.AuthRepository
import app.clipo.shared.auth.TokenStore
import app.clipo.shared.db.ClipoDatabase
import app.clipo.shared.db.NoteCache
import app.clipo.shared.repo.NotesRepository
import io.ktor.client.engine.HttpClientEngine

class ClipoClient(
    driver: SqlDriver,
    engine: HttpClientEngine,
    tokenStore: TokenStore,
) {
    private val sqlDriver = driver
    private val api = ClipoApi(engine)
    private val cache = NoteCache(ClipoDatabase(driver))
    val auth = AuthRepository(api, cache, tokenStore)
    val notes = NotesRepository(auth, cache)

    fun close() {
        api.close()
        sqlDriver.close()
    }
}
