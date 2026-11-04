package app.clipo.shared.api

import io.ktor.http.URLBuilder
import io.ktor.http.URLProtocol
import io.ktor.http.Url
import io.ktor.http.encodedPath

class ServerAddress private constructor(
    val baseUrl: String,
) {
    fun endpoint(path: String): String {
        require(path.startsWith("/") && !path.startsWith("//"))
        return "$baseUrl/api/v1$path"
    }

    companion object {
        fun parse(value: String): ServerAddress {
            val raw = value.trim()
            require(raw.startsWith("http://", true) || raw.startsWith("https://", true))
            require(raw.none { it.isWhitespace() || it == '\\' || it.code < 32 })
            val url = Url(raw)
            require(url.protocol == URLProtocol.HTTP || url.protocol == URLProtocol.HTTPS)
            require(url.host.isNotBlank() && url.user == null && url.password == null)
            require(url.parameters.isEmpty() && url.fragment.isEmpty())
            val normalized =
                URLBuilder(url)
                    .apply {
                        host = host.lowercase()
                        encodedPath = encodedPath.trimEnd('/').removeSuffix("/api/v1")
                    }.buildString()
                    .trimEnd('/')
            return ServerAddress(normalized)
        }
    }
}
