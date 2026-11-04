package app.clipo.shared

import app.cash.sqldelight.driver.native.NativeSqliteDriver
import app.clipo.shared.auth.TokenStore
import app.clipo.shared.db.ClipoDatabase
import io.ktor.client.engine.darwin.Darwin

fun createIosClient(tokenStore: TokenStore): ClipoClient {
    val driver = NativeSqliteDriver(ClipoDatabase.Schema, "clipo.db")
    driver.execute(null, "PRAGMA foreign_keys = ON", 0)
    return ClipoClient(driver, Darwin.create(), tokenStore)
}
