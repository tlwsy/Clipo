package app.clipo.shared

import app.clipo.shared.model.generated.CapturedContent
import app.clipo.shared.model.generated.ContentInline
import app.clipo.shared.model.generated.ReadingStylePatch
import app.clipo.shared.reading.ReaderDocument
import app.clipo.shared.reading.ReadingStyle
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import app.clipo.shared.model.generated.CapturedBlockOutput as Block

class ReadingTest {
    @Test
    fun themeOverrideResetsBaseWhileNullInherits() {
        val global = ReadingStyle.preset("focus").copy(fontSize = 24, fontFamily = "serif")
        assertEquals(global, ReadingStyle.resolve(global, ReadingStylePatch(fontSize = null)))
        val local = ReadingStyle.resolve(global, ReadingStylePatch(theme = "compact", paragraphSpacing = 0))
        assertEquals(16, local.fontSize)
        assertEquals("system-ui", local.fontFamily)
        assertEquals(0, local.paragraphSpacing)
        assertEquals(24, ReadingStyle.resolve(global, ReadingStylePatch(textAlign = "justify")).fontSize)
        assertEquals(18, ReadingStyle.resolve(null, null).fontSize)
        assertNull(ReadingStyle.edit(global, "font_size", "25"))
        assertNull(ReadingStyle.edit(global, "line_height", "NaN"))
        assertNull(ReadingStyle.edit(global, "text_color", "#fff"))
        assertNull(ReadingStyle.edit(global, "font_weight", "450"))
    }

    @Test
    fun hctAndSystemColorsMatchWebGoldenValues() {
        val style = ReadingStyle.preset("comfortable").copy(colorMode = "monet")
        assertEquals("#eaf8e6", ReadingStyle.colors(style, false).background)
        assertEquals("#172218", ReadingStyle.colors(style, true).background)
        assertEquals("#fafbf7", ReadingStyle.colors(style.copy(colorMode = "system"), false).background)
        assertEquals(
            ReadingStyle.colors(style.copy(monetScheme = "light"), false),
            ReadingStyle.colors(style.copy(monetScheme = "light"), true),
        )
    }

    @Test
    fun preorderIncludesStructuralBlocksAndPreservesUtf16() {
        val blocks =
            ReaderDocument.index(
                listOf(
                    Block(
                        "details",
                        children =
                            listOf(
                                Block(
                                    "list",
                                    ordered = true,
                                    children =
                                        listOf(
                                            Block(
                                                "list_item",
                                                inlines =
                                                    listOf(
                                                        ContentInline("中文😀"),
                                                        ContentInline("e\u0301", bold = true),
                                                    ),
                                            ),
                                            Block("list_item", text = "second"),
                                        ),
                                ),
                            ),
                    ),
                    Block(
                        "table",
                        children = listOf(Block("table_row", children = listOf(Block("table_cell", text = "cell")))),
                    ),
                    Block("image", url = "https://example.com/image.png"),
                    Block("code", text = "raw", inlines = listOf(ContentInline("ignored"))),
                ),
            )
        assertEquals(listOf(0, 4, 7, 8), blocks.map { it.index })
        val item =
            blocks
                .first()
                .children
                .first()
                .children
                .first()
        assertEquals(2, item.index)
        assertEquals("1. ", item.prefix)
        assertEquals("中文😀e\u0301", item.text)
        assertEquals("中文😀", ReaderDocument.utf16Slice(item.text, 0, 4))
        assertNull(ReaderDocument.utf16Slice(item.text, 2, 3))
        assertNull(ReaderDocument.utf16Slice(item.text, 3, 4))
        assertNull(ReaderDocument.utf16Slice(item.text, -1, 2))
        assertEquals("e\u0301", ReaderDocument.utf16Slice(item.text, 4, 6))
        assertEquals("raw", blocks.last().text)
        val old = ReaderDocument.blocks(CapturedContent("https://example.com", title = "old", text = "a\n\nb"))
        assertEquals(1, old.size)
        assertEquals("a\n\nb", old.single().text)
    }

    @Test
    fun legacyImagesAreVisibleWithoutDuplicatingInlineImages() {
        val image = "https://example.com/a.png"
        val extra = "https://example.com/b.png"
        val content =
            CapturedContent(
                "https://example.com",
                title = "old",
                text = "body",
                images = listOf(image, extra, extra, "http://localhost/a"),
                blocks = listOf(Block("details", children = listOf(Block("image", url = image)))),
            )
        assertEquals(listOf(extra), ReaderDocument.extraImages(content))
        assertEquals(listOf(image, extra), ReaderDocument.extraImages(content.copy(blocks = emptyList())))
    }

    @Test
    fun safeMarkdownDoesNotExecuteHtmlOrUnsafeLinks() {
        val blocks =
            ReaderDocument.markdown(
                "# Title\n\n**bold** and [bad](javascript:alert)\n\n```kt\nx < 2\n```\n\n<script>noop</script>",
            )
        assertEquals(listOf("heading", "text", "code", "text"), blocks.map { it.kind })
        assertTrue(blocks[1].inlines.first().bold)
        assertNull(blocks[1].inlines.last().url)
        assertEquals("<script>noop</script>", blocks.last().text)
        listOf(
            "file:///tmp/x",
            "https://localhost/a",
            "https://u:p@example.com",
            "https://127.0.0.1/a",
            "https://example.com:8000",
            "https://example.com/\\x",
        ).forEach { assertNull(ReaderDocument.safeUrl(it)) }
        assertEquals("https://example.com/path", ReaderDocument.safeUrl("https://example.com/path"))
    }
}
