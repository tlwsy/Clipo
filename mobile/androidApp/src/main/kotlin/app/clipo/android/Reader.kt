package app.clipo.android

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.Typeface
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.clipo.shared.MobileModel
import app.clipo.shared.MobileState
import app.clipo.shared.model.generated.ReadingPreferences
import app.clipo.shared.reading.ReaderBlock
import app.clipo.shared.reading.ReaderDocument
import app.clipo.shared.reading.ReadingStyle
import coil3.compose.AsyncImage

internal fun readingColor(value: String): Color = Color(android.graphics.Color.parseColor(value))

@Composable
internal fun readerTextStyle(style: ReadingPreferences): TextStyle {
    val context = LocalContext.current
    val family =
        remember(style.fontFamily, style.onlineFont, style.fontWeight) {
            when (style.fontFamily) {
                "serif" -> FontFamily.Serif
                "sans-serif" -> FontFamily.SansSerif
                "online" -> {
                    val serif = style.onlineFont?.family?.contains("Serif", ignoreCase = true) == true
                    val name = if (serif) "ClipoReadingSerif.ttf" else "ClipoReadingSans.ttf"
                    val face =
                        android.graphics.Typeface
                            .Builder(context.assets, name)
                            .setFontVariationSettings("'wght' ${style.fontWeight}")
                            .build()
                    FontFamily(Typeface(face))
                }
                else -> FontFamily.Default
            }
        }
    return TextStyle(
        fontFamily = family,
        fontSize = style.fontSize.toInt().sp,
        fontWeight = FontWeight(style.fontWeight.toInt()),
        lineHeight = (style.fontSize * style.lineHeight).sp,
        textAlign = if (style.textAlign == "justify") TextAlign.Justify else TextAlign.Start,
    )
}

@Composable
internal fun Reader(
    state: MobileState,
    model: MobileModel,
) {
    val note = state.detail
    if (note == null) {
        Column(Modifier.padding(24.dp)) {
            Text(stringResource(if (state.failure == null) R.string.loading else R.string.not_cached))
            TextButton(onClick = { state.selectedId?.let(model::openNote) }) { Text(stringResource(R.string.retry)) }
        }
        return
    }
    val style = ReadingStyle.resolve(state.preferences ?: note.readingPreferences, note.displayOverrides)
    val colors = ReadingStyle.colors(style, isSystemInDarkTheme())
    val blocks = remember(note.content) { ReaderDocument.blocks(note.content) }
    val summary = remember(note.summaryMarkdown) { ReaderDocument.markdown(note.summaryMarkdown.orEmpty()) }
    Box(Modifier.fillMaxSize().background(readingColor(colors.background)), contentAlignment = Alignment.TopCenter) {
        CompositionLocalProvider(
            LocalContentColor provides readingColor(colors.text),
            LocalTextStyle provides readerTextStyle(style),
        ) {
            SelectionContainer {
                LazyColumn(
                    Modifier.widthIn(max = style.contentWidth.toInt().dp).fillMaxSize(),
                    contentPadding = PaddingValues(24.dp),
                    verticalArrangement = Arrangement.spacedBy(style.paragraphSpacing.toInt().dp),
                ) {
                    item {
                        Text(
                            note.title,
                            style =
                                LocalTextStyle.current.copy(
                                    fontSize = (style.fontSize * 1.6).sp,
                                    lineHeight = (style.fontSize * 1.9).sp,
                                    fontWeight = FontWeight.Bold,
                                ),
                            modifier = Modifier.semantics { heading() },
                        )
                    }
                    item {
                        Text(
                            listOfNotNull(
                                note.source.siteName ?: note.source.platform,
                                note.source.author,
                                note.source.publishedAt?.take(10),
                            ).joinToString(" · "),
                        )
                        SafeLink(note.url, note.url, readingColor(colors.accent))
                    }
                    item { SectionTitle(R.string.summary) }
                    if (summary.isEmpty()) item { Text(stringResource(R.string.no_summary)) }
                    items(
                        summary,
                        key = { "summary-${it.index}" },
                    ) { BlockView(it, style, readingColor(colors.accent)) }
                    items(note.keyPoints) { Text("• $it") }
                    item { SectionTitle(R.string.original) }
                    items(blocks, key = { "body-${it.index}" }) { BlockView(it, style, readingColor(colors.accent)) }
                    items(ReaderDocument.extraImages(note.content), key = { "image-$it" }) {
                        ReaderImage(it, "", readingColor(colors.accent))
                    }
                    if (note.commentInsights.isNotEmpty()) item { SectionTitle(R.string.comment_insights) }
                    items(note.commentInsights) { Text("• ${it.text}") }
                    if (note.comments.any { it.isValuable }) item { SectionTitle(R.string.comments) }
                    items(note.comments.filter { it.isValuable }, key = { "comment-${it.id}" }) { comment ->
                        Column(Modifier.padding(start = if (comment.parentSourceId == null) 0.dp else 16.dp)) {
                            Text(
                                listOfNotNull(
                                    comment.author,
                                    comment.aiScore?.let { stringResource(R.string.ai_score, it) },
                                ).joinToString(" · "),
                                fontWeight = FontWeight.Bold,
                            )
                            Text(comment.content)
                            comment.aiReason?.let { Text(it, fontStyle = FontStyle.Italic) }
                        }
                    }
                    if (note.annotations.isNotEmpty()) item { SectionTitle(R.string.my_annotations) }
                    items(note.annotations, key = { "annotation-${it.id}" }) {
                        Column {
                            Text("“${it.selectedText}”")
                            it.noteText?.let { text -> Text(text) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionTitle(label: Int) {
    Text(stringResource(label), fontWeight = FontWeight.Bold, modifier = Modifier.semantics { heading() })
}

@Composable
internal fun SafeLink(
    text: String,
    url: String?,
    accent: Color,
) {
    val safe = ReaderDocument.safeUrl(url)
    Text(
        buildAnnotatedString {
            if (safe == null) {
                append(text)
            } else {
                withLink(
                    LinkAnnotation.Url(
                        safe,
                        styles = TextLinkStyles(SpanStyle(color = accent, textDecoration = TextDecoration.Underline)),
                    ),
                ) { append(text) }
            }
        },
    )
}

@Composable
internal fun BlockView(
    block: ReaderBlock,
    style: ReadingPreferences,
    accent: Color,
) {
    when (block.kind) {
        "divider" -> HorizontalDivider(color = LocalContentColor.current.copy(alpha = 0.3f))
        "image" -> ReaderImage(block.url, block.alt, accent)
        "details" -> {
            var expanded by rememberSaveable(block.index) { mutableStateOf(false) }
            Column {
                TextButton(onClick = { expanded = !expanded }) {
                    Text(
                        (if (expanded) "▾ " else "▸ ") + block.text.ifBlank { stringResource(R.string.details) },
                        color = accent,
                    )
                }
                if (expanded) BlockChildren(block, style, accent)
            }
        }
        "table" ->
            Column(Modifier.horizontalScroll(rememberScrollState())) {
                block.children.forEach { row ->
                    Row {
                        row.children.forEach { cell ->
                            Box(
                                Modifier
                                    .width(
                                        180.dp,
                                    ).border(1.dp, LocalContentColor.current.copy(alpha = 0.25f))
                                    .padding(12.dp),
                            ) {
                                RichText(cell, accent, bold = cell.header)
                            }
                        }
                    }
                }
            }
        "code" ->
            Text(
                block.text,
                Modifier
                    .fillMaxWidth()
                    .background(LocalContentColor.current.copy(alpha = 0.06f))
                    .horizontalScroll(rememberScrollState())
                    .padding(12.dp),
                fontFamily = FontFamily.Monospace,
                textAlign = TextAlign.Start,
            )
        "game_card" ->
            Column(Modifier.border(1.dp, accent).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                block.image?.let { ReaderImage(it, block.alt, accent) }
                SafeLink(block.text, block.url, accent)
            }
        else ->
            Column(
                Modifier.padding(start = if (block.kind == "quote") 16.dp else 0.dp),
                verticalArrangement = Arrangement.spacedBy(style.paragraphSpacing.toInt().dp),
            ) {
                if (block.text.isNotEmpty()) {
                    if (block.kind == "heading") {
                        val size = style.fontSize * (1.65 - block.level * 0.1)
                        CompositionLocalProvider(
                            LocalTextStyle provides
                                LocalTextStyle.current.copy(
                                    fontSize = size.sp,
                                    lineHeight = (size * style.lineHeight).sp,
                                ),
                        ) { RichText(block, accent, bold = true) }
                    } else {
                        RichText(block, accent, bold = block.header)
                    }
                }
                BlockChildren(block, style, accent)
            }
    }
}

@Composable
private fun BlockChildren(
    block: ReaderBlock,
    style: ReadingPreferences,
    accent: Color,
) {
    Column(
        Modifier.padding(start = if (block.kind == "list_item") 16.dp else 0.dp),
        verticalArrangement = Arrangement.spacedBy(style.paragraphSpacing.toInt().dp),
    ) {
        block.children.forEach { BlockView(it, style, accent) }
    }
}

@Composable
private fun RichText(
    block: ReaderBlock,
    accent: Color,
    bold: Boolean = false,
) {
    val modifier = if (block.kind == "heading") Modifier.semantics { heading() } else Modifier
    Text(
        buildAnnotatedString {
            append(block.prefix)
            if (block.inlines.isEmpty()) {
                append(block.text)
            } else {
                block.inlines.forEach { inline ->
                    withStyle(
                        SpanStyle(
                            fontWeight = if (inline.bold) FontWeight.Bold else null,
                            fontStyle = if (inline.italic) FontStyle.Italic else null,
                            fontFamily = if (inline.code) FontFamily.Monospace else null,
                            textDecoration = if (inline.strike) TextDecoration.LineThrough else null,
                        ),
                    ) {
                        val url = inline.url
                        if (url == null) {
                            append(inline.text)
                        } else {
                            withLink(
                                LinkAnnotation.Url(
                                    url,
                                    styles =
                                        TextLinkStyles(
                                            SpanStyle(color = accent, textDecoration = TextDecoration.Underline),
                                        ),
                                ),
                            ) { append(inline.text) }
                        }
                    }
                }
            }
        },
        modifier,
        fontWeight = if (bold) FontWeight.Bold else null,
    )
}

@Composable
private fun ReaderImage(
    url: String?,
    alt: String,
    accent: Color,
) {
    var failed by remember(url) { mutableStateOf(false) }
    Column {
        if (url != null &&
            !failed
        ) {
            AsyncImage(
                model = url,
                contentDescription = alt.ifBlank { stringResource(R.string.image) },
                modifier = Modifier.fillMaxWidth().heightIn(min = 96.dp, max = 420.dp),
                onError = { failed = true },
            )
        }
        if (failed || url == null) Text(stringResource(R.string.image_unavailable))
        if (alt.isNotBlank()) Text(alt)
        if (url != null) SafeLink(stringResource(R.string.open_image), url, accent)
        if (failed) TextButton(onClick = { failed = false }) { Text(stringResource(R.string.retry)) }
    }
}
