package app.clipo.shared.auth

import app.clipo.shared.api.ApiException
import app.clipo.shared.api.ApiResult
import app.clipo.shared.api.ClipoApi
import app.clipo.shared.api.Failure
import app.clipo.shared.api.FailureKind
import app.clipo.shared.api.ServerAddress
import app.clipo.shared.api.accountChanged
import app.clipo.shared.api.resultOf
import app.clipo.shared.api.wireJson
import app.clipo.shared.db.Account
import app.clipo.shared.db.NoteCache
import app.clipo.shared.model.generated.LoginRequest
import app.clipo.shared.model.generated.RefreshRequest
import app.clipo.shared.model.generated.SessionResponse
import app.clipo.shared.model.generated.VersionResponse
import io.ktor.http.HttpMethod
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.encodeToString

data class AccountInfo(
    val server: String,
    val userId: Long,
    val username: String,
    val generation: String,
    val serverVersion: String,
)

internal fun Account.info(): AccountInfo = AccountInfo(server_id, user_id, username, generation, server_version)

class AuthRepository internal constructor(
    private val api: ClipoApi,
    private val cache: NoteCache,
    private val tokens: TokenStore,
) {
    private val mutex = Mutex()
    private var accessToken: String? = null
    private val mutableAccount = MutableStateFlow(cache.account()?.info())
    val account: StateFlow<AccountInfo?> = mutableAccount.asStateFlow()
    private val mutableNeedsLogin = MutableStateFlow(false)
    val needsLogin: StateFlow<Boolean> = mutableNeedsLogin.asStateFlow()

    suspend fun inspectServer(value: String): ApiResult<VersionResponse> =
        resultOf {
            val server = parseServer(value)
            wireJson.decodeFromString(api.request(server, "/meta/version"))
        }

    suspend fun login(
        value: String,
        username: String,
        password: String,
    ): ApiResult<AccountInfo> =
        resultOf {
            mutex.withLock {
                val server = parseServer(value)
                val version = wireJson.decodeFromString<VersionResponse>(api.request(server, "/meta/version"))
                if (!version.setupCompleted) {
                    throw ApiException(Failure(FailureKind.PERMANENT, "setup_required", "请先在网页完成服务器初始化"))
                }
                val session =
                    wireJson.decodeFromString<SessionResponse>(
                        api.request(
                            server,
                            "/auth/login",
                            HttpMethod.Post,
                            wireJson.encodeToString(LoginRequest(username, password)),
                        ),
                    )
                // Write the secure token first; a failed secure write never creates an apparently logged-in account.
                persist(server, session)
                val owner = cache.accept(server.baseUrl, session.user, version.version).info()
                accessToken = session.accessToken
                mutableAccount.value = owner
                mutableNeedsLogin.value = false
                owner
            }
        }

    internal suspend fun authorized(
        owner: AccountInfo,
        path: String,
        parameters: Map<String, String> = emptyMap(),
    ): String {
        val used = token(owner)
        val server = ServerAddress.parse(owner.server)
        return try {
            api.request(server, path, token = used, parameters = parameters).also { verify(owner) }
        } catch (error: ApiException) {
            if (error.status != 401) throw error
            val renewed = token(owner, used)
            try {
                api.request(server, path, token = renewed, parameters = parameters).also { verify(owner) }
            } catch (retry: ApiException) {
                if (retry.status == 401) {
                    mutex.withLock {
                        verify(owner)
                        expire()
                    }
                }
                throw retry
            }
        }
    }

    private suspend fun token(
        owner: AccountInfo,
        rejected: String? = null,
    ): String =
        mutex.withLock {
            verify(owner)
            val current = accessToken
            if (current != null && current != rejected) return@withLock current
            val saved = tokens.read()?.let { runCatching { wireJson.decodeFromString<SavedToken>(it) }.getOrNull() }
            if (saved == null ||
                saved.server != owner.server ||
                saved.userId != owner.userId ||
                saved.username != owner.username
            ) {
                expire()
                accountChanged()
            }
            val server = ServerAddress.parse(owner.server)
            val session =
                try {
                    wireJson.decodeFromString<SessionResponse>(
                        api.request(
                            server,
                            "/auth/refresh",
                            HttpMethod.Post,
                            wireJson.encodeToString(RefreshRequest(saved.refreshToken)),
                        ),
                    )
                } catch (error: ApiException) {
                    // Transient network/server errors must retain the rotating token and cached data.
                    if (error.status in listOf(400, 401, 403)) expire()
                    throw error
                }
            if (session.user.id != owner.userId || session.user.username != owner.username) {
                expire()
                accountChanged()
            }
            persist(server, session)
            accessToken = session.accessToken
            mutableNeedsLogin.value = false
            session.accessToken
        }

    suspend fun logout(): ApiResult<Unit> =
        resultOf {
            mutex.withLock {
                val saved = tokens.read()?.let { runCatching { wireJson.decodeFromString<SavedToken>(it) }.getOrNull() }
                // Local sign-out is unconditional, including when the server is unreachable.
                expire()
                cache.clear()
                mutableAccount.value = null
                mutableNeedsLogin.value = false
                if (saved != null) {
                    api.request(
                        ServerAddress.parse(saved.server),
                        "/auth/logout",
                        HttpMethod.Post,
                        wireJson.encodeToString(RefreshRequest(saved.refreshToken)),
                    )
                }
            }
        }

    private fun verify(owner: AccountInfo) {
        if (mutableAccount.value != owner || cache.account()?.generation != owner.generation) accountChanged()
    }

    private fun persist(
        server: ServerAddress,
        session: SessionResponse,
    ) {
        check(
            tokens.write(
                wireJson.encodeToString(
                    SavedToken(server.baseUrl, session.user.id, session.user.username, session.refreshToken),
                ),
            ),
        )
    }

    private fun expire() {
        accessToken = null
        check(tokens.clear())
        mutableNeedsLogin.value = true
    }

    private fun parseServer(value: String): ServerAddress =
        try {
            ServerAddress.parse(value)
        } catch (_: IllegalArgumentException) {
            throw ApiException(Failure(FailureKind.PERMANENT, "invalid_server", "请输入不含账号、查询参数或片段的 HTTP(S) 服务器地址"))
        }
}
