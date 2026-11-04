package app.clipo.shared

import app.clipo.shared.api.ServerAddress
import app.clipo.shared.api.retryAfterSeconds
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class ServerAddressTest {
    @Test
    fun retryAfterSupportsSecondsAndHttpDate() {
        assertEquals(12L, retryAfterSeconds("12"))
        assertEquals(1L, retryAfterSeconds("Thu, 01 Jan 1970 00:00:02 GMT", 1001))
        assertEquals(null, retryAfterSeconds("invalid"))
    }

    @Test
    fun normalizesBaseAndApiSuffix() {
        assertEquals("https://example.com/clipo", ServerAddress.parse(" https://EXAMPLE.com/clipo/api/v1/ ").baseUrl)
        assertEquals(
            "http://10.0.2.2:18000/api/v1/notes",
            ServerAddress.parse("http://10.0.2.2:18000").endpoint("/notes"),
        )
    }

    @Test
    fun rejectsAmbiguousOrCredentialBearingAddresses() {
        listOf(
            "file:///notes",
            "example.com",
            "https://u:p@host",
            "https://host?q=1",
            "https://host#x",
            "https://host\\@evil",
        ).forEach {
            assertFailsWith<IllegalArgumentException> { ServerAddress.parse(it) }
        }
    }
}
