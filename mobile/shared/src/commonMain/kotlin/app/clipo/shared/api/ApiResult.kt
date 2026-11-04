package app.clipo.shared.api

import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException

enum class FailureKind { RETRYABLE, AUTHENTICATION, PERMANENT }

data class Failure(
    val kind: FailureKind,
    val code: String,
    val message: String,
    val retryAfterSeconds: Long? = null,
)

sealed class ApiResult<out T> {
    data class Success<T>(
        val value: T,
    ) : ApiResult<T>()

    data class Error(
        val failure: Failure,
    ) : ApiResult<Nothing>()
}

internal class ApiException(
    val failure: Failure,
    val status: Int = 0,
) : Exception(failure.code)

internal suspend fun <T> resultOf(block: suspend () -> T): ApiResult<T> =
    try {
        ApiResult.Success(block())
    } catch (error: CancellationException) {
        throw error
    } catch (error: ApiException) {
        ApiResult.Error(error.failure)
    } catch (_: SerializationException) {
        ApiResult.Error(Failure(FailureKind.PERMANENT, "incompatible_server", "服务器数据格式不兼容，请检查服务器与 App 版本"))
    } catch (_: Exception) {
        // Never forward exception text: transports may include URLs or response bodies.
        ApiResult.Error(Failure(FailureKind.RETRYABLE, "connection_failed", "无法连接服务器，请稍后重试"))
    }

internal fun accountChanged(): Nothing =
    throw ApiException(
        Failure(FailureKind.AUTHENTICATION, "account_changed", "账号已改变，请重新登录"),
    )
