package app.clipo.shared

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import app.clipo.shared.api.ApiResult
import app.clipo.shared.auth.TokenStore
import app.clipo.shared.db.ClipoDatabase
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import java.nio.file.Files

/** Invoked only by scripts/smoke_mobile.py against a temporary, isolated backend. */
fun main() =
    runBlocking {
        val base = checkNotNull(System.getenv("CLIPO_MOBILE_SMOKE_URL"))
        check(base.startsWith("http://127.0.0.1:"))
        val tokens =
            object : TokenStore {
                private var token: String? = null

                override fun read(): String? = token

                override fun write(value: String): Boolean {
                    token = value
                    return true
                }

                override fun clear(): Boolean {
                    token = null
                    return true
                }
            }
        val path = Files.createTempFile("clipo-mobile-smoke", ".db")

        fun database(create: Boolean): JdbcSqliteDriver =
            JdbcSqliteDriver("jdbc:sqlite:$path").also {
                if (create) ClipoDatabase.Schema.create(it)
                it.execute(null, "PRAGMA foreign_keys = ON", 0)
            }
        val client = ClipoClient(database(true), OkHttp.create(), tokens)
        val id: Long
        try {
            check(client.auth.login(base, "mobile-test", "mobile-test-password") is ApiResult.Success)
            check(client.notes.refresh() is ApiResult.Success)
            id =
                client.notes.notes
                    .first()
                    .single()
                    .id
            check(client.notes.refreshDetail(id) is ApiResult.Success)
            val detail = checkNotNull(client.notes.detail(id).first())
            check(detail.title == "Mobile acceptance")
            check(detail.content.text.contains("中文😀"))
            check(detail.annotations.single().selectedText == "中文😀")
            check(detail.readingPreferences != null)
        } finally {
            client.close()
        }
        // A fresh client must rotate the saved token, then read the same note through the real API.
        val renewed = ClipoClient(database(false), OkHttp.create(), tokens)
        try {
            check(renewed.notes.refresh() is ApiResult.Success)
        } finally {
            renewed.close()
        }
        val offline = ClipoClient(database(false), MockEngine { error("offline") }, tokens)
        try {
            check(
                offline.notes.notes
                    .first()
                    .single()
                    .id == id,
            )
            check(
                offline.notes
                    .detail(id)
                    .first()
                    ?.content
                    ?.text
                    ?.contains("中文😀") == true,
            )
            check(offline.notes.refresh() is ApiResult.Error)
            check(
                offline.notes
                    .detail(id)
                    .first()
                    ?.annotations
                    ?.size == 1,
            )
            offline.auth.logout()
            check(
                offline.notes.notes
                    .first()
                    .isEmpty(),
            )
            check(tokens.read() == null)
        } finally {
            offline.close()
            Files.deleteIfExists(path)
        }
        println("Mobile HTTP login, token rotation, notes, annotations, disk restart, offline cache and logout passed")
    }
