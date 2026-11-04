package app.clipo.shared.auth

import kotlinx.serialization.Serializable

/** Implementations must persist atomically in platform secure storage, never in the cache DB. */
interface TokenStore {
    fun read(): String?

    fun write(value: String): Boolean

    fun clear(): Boolean
}

@Serializable
internal data class SavedToken(
    val server: String,
    val userId: Long,
    val username: String,
    val refreshToken: String,
)
