package app.clipo.shared

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import app.clipo.shared.api.ApiResult
import app.clipo.shared.api.FailureKind
import app.clipo.shared.api.wireJson
import app.clipo.shared.auth.TokenStore
import app.clipo.shared.db.ClipoDatabase
import app.clipo.shared.db.NoteCache
import app.clipo.shared.model.generated.NoteItem
import app.clipo.shared.model.generated.NotePage
import app.clipo.shared.model.generated.UserResponse
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.encodeToString
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

private class MemoryTokens : TokenStore {
    var value: String? = null

    override fun read(): String? = value

    override fun write(value: String): Boolean {
        this.value = value
        return true
    }

    override fun clear(): Boolean {
        value = null
        return true
    }
}

class RepositoryTest {
    private val version = """{"version":"0.1.0","setup_completed":true,"registration_open":false}"""

    private fun session(
        id: Long = 1,
        access: String = "access",
        refresh: String = "refresh",
    ): String =
        """{"access_token":"$access","refresh_token":"$refresh","expires_in":60,"user":{"id":$id,"username":"user$id","email":"u$id@example.com","is_admin":false}}"""

    private fun item(id: Long): NoteItem =
        NoteItem(
            id,
            "笔记$id",
            "https://example.com/$id",
            "web",
            null,
            null,
            "摘要",
            "ready",
            "2026-11-04",
            false,
            emptyList(),
        )

    private fun driver(
        url: String = JdbcSqliteDriver.IN_MEMORY,
        create: Boolean = true,
    ): JdbcSqliteDriver =
        JdbcSqliteDriver(url).also {
            if (create) ClipoDatabase.Schema.create(it)
            it.execute(null, "PRAGMA foreign_keys = ON", 0)
        }

    private fun engine(handler: suspend (HttpRequestData) -> Pair<Int, String>): MockEngine =
        MockEngine { request ->
            val (status, body) = handler(request)
            respond(
                body,
                HttpStatusCode.fromValue(status),
                headersOf(
                    "Content-Type" to listOf("application/json"),
                    "Retry-After" to listOf("17"),
                ),
            )
        }

    @Test
    fun concurrentUnauthorizedRequestsRotateOnlyOnce() =
        runTest {
            val tokens = MemoryTokens()
            var refreshes = 0
            val client =
                ClipoClient(
                    driver(),
                    engine { request ->
                        when (request.url.encodedPath) {
                            "/api/v1/meta/version" -> 200 to version
                            "/api/v1/auth/login" -> 200 to session()
                            "/api/v1/auth/refresh" -> {
                                refreshes++
                                delay(50)
                                200 to session(access = "renewed", refresh = "rotated")
                            }
                            else ->
                                if (request.headers["Authorization"] ==
                                    "Bearer renewed"
                                ) {
                                    200 to "{}"
                                } else {
                                    401 to "{}"
                                }
                        }
                    },
                    tokens,
                )
            try {
                assertIs<ApiResult.Success<*>>(client.auth.login("https://example.com", "user1", "password"))
                val owner = client.auth.account.value!!
                List(12) { async { client.auth.authorized(owner, "/auth/me") } }.awaitAll()
                assertEquals(1, refreshes)
                assertTrue(tokens.value!!.contains("rotated"))
                assertFalse(tokens.value!!.contains("renewed"))
            } finally {
                client.close()
            }
        }

    @Test
    fun transientRefreshFailureKeepsTokenAndAuthenticationFailureKeepsCache() =
        runTest {
            val tokens = MemoryTokens()
            var status = 200
            val client =
                ClipoClient(
                    driver(),
                    engine { request ->
                        when (request.url.encodedPath) {
                            "/api/v1/meta/version" -> 200 to version
                            "/api/v1/auth/login" -> 200 to session()
                            "/api/v1/auth/refresh" -> status to "{}"
                            else ->
                                if (status ==
                                    200
                                ) {
                                    200 to wireJson.encodeToString(NotePage(listOf(item(1)), null))
                                } else {
                                    401 to "{}"
                                }
                        }
                    },
                    tokens,
                )
            try {
                client.auth.login("https://example.com", "user1", "password")
                client.notes.refresh()
                status = 503
                assertEquals(FailureKind.RETRYABLE, assertIs<ApiResult.Error>(client.notes.refresh()).failure.kind)
                assertTrue(tokens.value != null)
                assertEquals(
                    1,
                    client.notes.notes
                        .first()
                        .size,
                )
                status = 401
                assertEquals(FailureKind.AUTHENTICATION, assertIs<ApiResult.Error>(client.notes.refresh()).failure.kind)
                assertNull(tokens.value)
                assertTrue(client.auth.needsLogin.value)
                assertEquals(
                    1,
                    client.notes.notes
                        .first()
                        .size,
                )
            } finally {
                client.close()
            }
        }

    @Test
    fun lateResponseCannotWriteIntoNewAccount() =
        runTest {
            val requested = CompletableDeferred<Unit>()
            val release = CompletableDeferred<Unit>()
            var userId = 1L
            val client =
                ClipoClient(
                    driver(),
                    engine { request ->
                        when (request.url.encodedPath) {
                            "/api/v1/meta/version" -> 200 to version
                            "/api/v1/auth/login" -> 200 to session(userId)
                            else -> {
                                requested.complete(Unit)
                                release.await()
                                200 to wireJson.encodeToString(NotePage(listOf(item(1)), null))
                            }
                        }
                    },
                    MemoryTokens(),
                )
            try {
                client.auth.login("https://example.com", "user1", "password")
                val old = client.auth.account.value!!
                val pending = async { client.notes.refresh() }
                requested.await()
                userId = 2
                client.auth.login("https://example.com", "user2", "password")
                release.complete(Unit)
                assertIs<ApiResult.Error>(pending.await())
                assertNotEquals(
                    old.generation,
                    client.auth.account.value!!
                        .generation,
                )
                assertTrue(
                    client.notes.notes
                        .first()
                        .isEmpty(),
                )
            } finally {
                client.close()
            }
        }

    @Test
    fun restartWithoutNetworkReadsDiskAndNeverStoresTokensInDatabase() =
        runTest {
            val path = Files.createTempFile("clipo-cache", ".db")
            val tokens = MemoryTokens()
            val initial =
                ClipoClient(
                    driver("jdbc:sqlite:$path"),
                    engine { request ->
                        when (request.url.encodedPath) {
                            "/api/v1/meta/version" -> 200 to version
                            "/api/v1/auth/login" -> 200 to session()
                            else -> 200 to wireJson.encodeToString(NotePage(listOf(item(42)), null))
                        }
                    },
                    tokens,
                )
            initial.auth.login("https://example.com", "user1", "password")
            initial.notes.refresh()
            initial.close()
            val reopened = ClipoClient(driver("jdbc:sqlite:$path", false), MockEngine { error("offline") }, tokens)
            try {
                assertEquals(
                    42,
                    reopened.notes.notes
                        .first()
                        .single()
                        .id,
                )
                assertIs<ApiResult.Error>(reopened.notes.refresh())
                assertEquals(
                    42,
                    reopened.notes.notes
                        .first()
                        .single()
                        .id,
                )
                assertFalse(Files.readString(path, Charsets.ISO_8859_1).contains("refresh_token"))
                reopened.auth.logout()
                assertNull(reopened.auth.account.value)
                assertNull(tokens.value)
                assertTrue(
                    reopened.notes.notes
                        .first()
                        .isEmpty(),
                )
            } finally {
                reopened.close()
                Files.deleteIfExists(path)
            }
        }

    @Test
    fun paginationAndAccountDeletionRespectGeneration() =
        runTest {
            val sql = driver()
            try {
                val cache = NoteCache(ClipoDatabase(sql))
                val first = cache.accept("https://one.test", UserResponse(1, "one", "one@example.com", false), "1")
                cache.savePage(first.generation, listOf(item(3), item(2)), "next", true)
                cache.savePage(first.generation, listOf(item(1)), null, false)
                assertEquals(listOf(3L, 2L, 1L), cache.notes(first.generation).first().map { it.id })
                cache.savePage(first.generation, listOf(item(3)), null, true)
                assertEquals(listOf(3L), cache.notes(first.generation).first().map { it.id })
                val second = cache.accept("https://two.test", UserResponse(1, "one", "one@example.com", false), "1")
                cache.savePage(first.generation, listOf(item(9)), null, true)
                assertTrue(cache.notes(first.generation).first().isEmpty())
                assertTrue(cache.notes(second.generation).first().isEmpty())
            } finally {
                sql.close()
            }
        }

    @Test
    fun rateLimitAndMalformedErrorsHaveSafeResult() =
        runTest {
            var response = 429 to """{"error":{"code":"rate_limited","message":"请求过于频繁","detail":{}}}"""
            val client = ClipoClient(driver(), engine { response }, MemoryTokens())
            try {
                val error = assertIs<ApiResult.Error>(client.auth.inspectServer("https://example.com"))
                assertEquals(17, error.failure.retryAfterSeconds)
                assertEquals("rate_limited", error.failure.code)
                response = 502 to "private-server-response"
                val fallback = assertIs<ApiResult.Error>(client.auth.inspectServer("https://example.com"))
                assertFalse(fallback.failure.message.contains("private"))
                response = 200 to "{}"
                val incompatible = assertIs<ApiResult.Error>(client.auth.inspectServer("https://example.com"))
                assertEquals("incompatible_server", incompatible.failure.code)
            } finally {
                client.close()
            }
        }
}
