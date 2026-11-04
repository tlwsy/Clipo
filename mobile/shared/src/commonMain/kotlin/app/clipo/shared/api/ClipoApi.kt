package app.clipo.shared.api

import app.clipo.shared.model.generated.ErrorResponse
import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.request
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.contentType
import io.ktor.http.fromHttpToGmtDate
import io.ktor.serialization.kotlinx.json.json
import io.ktor.util.date.GMTDate
import kotlinx.serialization.json.Json

internal val wireJson = Json { ignoreUnknownKeys = true }

internal class ClipoApi(
    private val engine: HttpClientEngine,
) {
    private val client =
        HttpClient(engine) {
            followRedirects = false
            expectSuccess = false
            install(ContentNegotiation) { json(wireJson) }
            install(HttpTimeout) {
                requestTimeoutMillis = 15_000
                connectTimeoutMillis = 10_000
                socketTimeoutMillis = 15_000
            }
        }

    suspend fun request(
        server: ServerAddress,
        path: String,
        method: HttpMethod = HttpMethod.Get,
        body: String? = null,
        token: String? = null,
        parameters: Map<String, String> = emptyMap(),
    ): String {
        val response =
            client.request(server.endpoint(path)) {
                this.method = method
                if (token != null) bearerAuth(token)
                url { parameters.forEach { (key, value) -> this.parameters.append(key, value) } }
                if (body != null) {
                    contentType(ContentType.Application.Json)
                    setBody(body)
                }
            }
        val status = response.status.value
        if (status in 200..299) return response.bodyAsText()
        val error = runCatching { wireJson.decodeFromString<ErrorResponse>(response.bodyAsText()).error }.getOrNull()
        val kind =
            when {
                status == 401 -> FailureKind.AUTHENTICATION
                status == 408 || status == 429 || status >= 500 -> FailureKind.RETRYABLE
                else -> FailureKind.PERMANENT
            }
        throw ApiException(
            Failure(
                kind,
                error?.code ?: "request_failed",
                error?.message ?: "请求未成功，请稍后重试",
                retryAfterSeconds(response.headers[HttpHeaders.RetryAfter]),
            ),
            status,
        )
    }

    fun close() {
        client.close()
        engine.close()
    }
}

internal fun retryAfterSeconds(
    value: String?,
    nowMillis: Long = GMTDate().timestamp,
): Long? {
    if (value == null) return null
    value.toLongOrNull()?.let { return it.coerceAtLeast(0) }
    return runCatching { ((value.fromHttpToGmtDate().timestamp - nowMillis + 999) / 1000).coerceAtLeast(0) }.getOrNull()
}
