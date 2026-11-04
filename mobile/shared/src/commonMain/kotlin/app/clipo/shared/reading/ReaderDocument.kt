package app.clipo.shared.reading

import app.clipo.shared.model.generated.CapturedBlockOutput
import app.clipo.shared.model.generated.CapturedContent
import app.clipo.shared.model.generated.ContentInline
import io.ktor.http.Url

/** Stable pre-order IDs include containers; display decoration never changes source offsets. */
data class ReaderBlock(
    val index: Int,
    val kind: String,
    val text: String,
    val inlines: List<ContentInline>,
    val children: List<ReaderBlock>,
    val url: String?,
    val image: String?,
    val alt: String,
    val level: Int,
    val prefix: String,
    val header: Boolean,
)

object ReaderDocument {
    fun blocks(content: CapturedContent): List<ReaderBlock> =
        index(
            content.blocks.ifEmpty { listOf(CapturedBlockOutput("text", text = content.text)) },
        )

    fun index(blocks: List<CapturedBlockOutput>): List<ReaderBlock> {
        var next = 0

        fun visit(
            rows: List<CapturedBlockOutput>,
            ordered: Boolean = false,
        ): List<ReaderBlock> =
            rows.mapIndexed { position, block ->
                val id = next++
                ReaderBlock(
                    id,
                    block.type,
                    text(block),
                    block.inlines.map { it.copy(url = safeUrl(it.url)) },
                    visit(block.children, block.ordered),
                    safeUrl(block.url),
                    safeUrl(block.image),
                    block.alt,
                    block.level.toInt().coerceIn(1, 6),
                    if (block.type == "list_item") {
                        if (ordered) "${position + 1}. " else "• "
                    } else {
                        ""
                    },
                    block.header,
                )
            }
        return visit(blocks)
    }

    fun text(block: CapturedBlockOutput): String =
        if (block.type == "code" || block.inlines.isEmpty()) block.text else block.inlines.joinToString("") { it.text }

    fun utf16Slice(
        text: String,
        start: Int,
        end: Int,
    ): String? {
        fun boundary(offset: Int): Boolean =
            offset == 0 ||
                offset == text.length ||
                !(text[offset - 1].isHighSurrogate() && text[offset].isLowSurrogate())
        return if (start < 0 || end > text.length || start >= end || !boundary(start) || !boundary(end)) {
            null
        } else {
            text.substring(start, end)
        }
    }

    /** Match the web reader: only external HTTP(S) links; no credentials, custom schemes or local hosts. */
    fun safeUrl(value: String?): String? {
        if (value.isNullOrBlank() || value.any { it <= ' ' || it == '\\' }) return null
        val url = runCatching { Url(value) }.getOrNull() ?: return null
        val host = url.host.lowercase().trimEnd('.')
        if (url.protocol.name !in listOf("http", "https") ||
            url.port !in listOf(80, 443) ||
            url.user != null ||
            url.password != null ||
            host.isBlank() ||
            Regex(
                "^(localhost|127\\.|10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.|\\[|0\\.|169\\.254\\.)",
            ).containsMatchIn(host) ||
            host.any { it == ':' } ||
            host.endsWith(".local") ||
            host.endsWith(".internal") ||
            host.endsWith(".localhost")
        ) {
            return null
        }
        return value
    }

    /** Safe Markdown subset: no HTML, embeds or automatic images; unsupported syntax remains text. */
    fun markdown(source: String): List<ReaderBlock> {
        val blocks = mutableListOf<CapturedBlockOutput>()
        val paragraph = mutableListOf<String>()
        var code: MutableList<String>? = null

        fun flush() {
            if (paragraph.isNotEmpty()) {
                blocks.add(CapturedBlockOutput("text", inlines = inlineMarkdown(paragraph.joinToString("\n"))))
                paragraph.clear()
            }
        }
        source.lines().forEach { line ->
            when {
                line.startsWith("```") -> {
                    flush()
                    val current = code
                    if (current == null) {
                        code = mutableListOf()
                    } else {
                        blocks.add(CapturedBlockOutput("code", text = current.joinToString("\n")))
                        code = null
                    }
                }
                code != null -> code?.add(line)
                line.isBlank() -> flush()
                Regex("^#{1,6} ").containsMatchIn(line) -> {
                    flush()
                    blocks.add(
                        CapturedBlockOutput(
                            "heading",
                            level = line.takeWhile { it == '#' }.length.toLong(),
                            inlines = inlineMarkdown(line.substringAfter(' ')),
                        ),
                    )
                }
                line in listOf("---", "***", "___") -> {
                    flush()
                    blocks.add(CapturedBlockOutput("divider"))
                }
                line.startsWith("> ") -> {
                    flush()
                    blocks.add(CapturedBlockOutput("quote", inlines = inlineMarkdown(line.drop(2))))
                }
                Regex("^([-*+] |\\d+\\. )").containsMatchIn(line) -> {
                    flush()
                    blocks.add(CapturedBlockOutput("text", inlines = inlineMarkdown(line)))
                }
                else -> paragraph.add(line)
            }
        }
        code?.let { blocks.add(CapturedBlockOutput("code", text = it.joinToString("\n"))) }
        flush()
        return index(blocks)
    }

    private fun inlineMarkdown(text: String): List<ContentInline> {
        val pattern =
            Regex(
                "(`[^`\\n]+`|\\*\\*[^*\\n]+\\*\\*|__[^_\\n]+__|~~[^~\\n]+~~|\\*[^*\\n]+\\*|\\[[^]\\n]+]\\([^ )\\n]+\\))",
            )
        val result = mutableListOf<ContentInline>()
        var offset = 0
        pattern.findAll(text).forEach { match ->
            if (match.range.first > offset) result.add(ContentInline(text.substring(offset, match.range.first)))
            val part = match.value
            result.add(
                when {
                    part.startsWith('`') -> ContentInline(part.drop(1).dropLast(1), code = true)
                    part.startsWith(
                        "**",
                    ) ||
                        part.startsWith("__") -> ContentInline(part.drop(2).dropLast(2), bold = true)
                    part.startsWith("~~") -> ContentInline(part.drop(2).dropLast(2), strike = true)
                    part.startsWith('*') -> ContentInline(part.drop(1).dropLast(1), italic = true)
                    else ->
                        ContentInline(
                            part.substringAfter('[').substringBefore(']'),
                            url = safeUrl(part.substringAfter("](").dropLast(1)),
                        )
                },
            )
            offset = match.range.last + 1
        }
        if (offset < text.length) result.add(ContentInline(text.substring(offset)))
        return result
    }
}
