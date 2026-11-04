package app.clipo.android

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import app.clipo.shared.MobileModel
import app.clipo.shared.MobileState
import app.clipo.shared.reading.ReadingStyle
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ReadingDialog(
    state: MobileState,
    model: MobileModel,
) {
    val draft = state.readingDraft ?: return
    val colors = ReadingStyle.colors(draft, isSystemInDarkTheme())
    var invalid by remember { mutableStateOf(emptySet<String>()) }
    LaunchedEffect(state.readingNoteId, draft.theme, draft.colorMode) { invalid = emptySet() }
    ModalBottomSheet(
        onDismissRequest = model::cancelReading,
        sheetState =
            rememberModalBottomSheetState(
                skipPartiallyExpanded = true,
                confirmValueChange = { !state.readingSaving },
            ),
    ) {
        Column(Modifier.fillMaxHeight(0.94f).padding(horizontal = 20.dp)) {
            Text(stringResource(R.string.reading_style), style = MaterialTheme.typography.headlineSmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = state.readingNoteId == null,
                    onClick = { model.beginReading(false) },
                    label = { Text(stringResource(R.string.global_scope)) },
                    enabled = !state.readingSaving,
                )
                if (state.detail != null) {
                    FilterChip(
                        selected = state.readingNoteId != null,
                        onClick = {
                            model.beginReading(true)
                        },
                        label = { Text(stringResource(R.string.note_scope)) },
                        enabled = !state.readingSaving,
                    )
                }
            }
            Box(Modifier.fillMaxWidth().background(readingColor(colors.background)).padding(16.dp)) {
                Text(
                    stringResource(R.string.style_preview),
                    style = readerTextStyle(draft),
                    color = readingColor(colors.text),
                )
            }
            if (state.readingSaving) LinearProgressIndicator(Modifier.fillMaxWidth())
            state.readingFailure?.let { Text(it.message, color = MaterialTheme.colorScheme.error) }
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    Choices(
                        R.string.theme,
                        draft.theme,
                        listOf("comfortable", "compact", "focus", "print"),
                        listOf(R.string.comfortable, R.string.compact, R.string.focus, R.string.print_theme),
                    ) { model.editReading("theme", it) }
                }
                item {
                    Choices(
                        R.string.color_mode,
                        draft.colorMode,
                        listOf("custom", "system", "monet"),
                        listOf(R.string.custom_colors, R.string.system_colors, R.string.monet_colors),
                    ) { model.editReading("color_mode", it) }
                }
                if (draft.colorMode == "custom") {
                    item {
                        ColorField(R.string.background_color, draft.backgroundColor, "background_color", model) {
                            invalid = if (it) invalid + "background" else invalid - "background"
                        }
                    }
                    item {
                        ColorField(R.string.text_color, draft.textColor, "text_color", model) {
                            invalid = if (it) invalid + "text" else invalid - "text"
                        }
                    }
                }
                if (draft.colorMode == "monet") {
                    item {
                        ColorField(R.string.seed_color, draft.monetSeed, "monet_seed", model) {
                            invalid = if (it) invalid + "seed" else invalid - "seed"
                        }
                    }
                    item {
                        Choices(
                            R.string.monet_scheme,
                            draft.monetScheme,
                            listOf("system", "light", "dark"),
                            listOf(R.string.system_colors, R.string.light, R.string.dark),
                        ) { model.editReading("monet_scheme", it) }
                    }
                }
                item {
                    Choices(
                        R.string.font,
                        draft.fontFamily,
                        listOf("system-ui", "serif", "sans-serif", "online"),
                        listOf(R.string.font_system, R.string.font_serif, R.string.font_sans, R.string.font_bundled),
                    ) { model.editReading("font_family", it) }
                    Text(stringResource(R.string.font_hint), style = MaterialTheme.typography.bodySmall)
                }
                item {
                    Choices(
                        R.string.weight,
                        draft.fontWeight.toString(),
                        listOf("400", "500", "600", "700"),
                        listOf(R.string.weight_400, R.string.weight_500, R.string.weight_600, R.string.weight_700),
                    ) { model.editReading("font_weight", it) }
                }
                item {
                    StyleSlider(R.string.font_size, draft.fontSize.toFloat(), 14f..24f, 9) {
                        model.editReading("font_size", it.roundToInt().toString())
                    }
                }
                item {
                    StyleSlider(R.string.line_height, draft.lineHeight.toFloat(), 1.2f..2f, 7) {
                        model.editReading("line_height", ((it * 10).roundToInt() / 10.0).toString())
                    }
                }
                item {
                    StyleSlider(R.string.paragraph_spacing, draft.paragraphSpacing.toFloat(), 0f..40f, 39) {
                        model.editReading("paragraph_spacing", it.roundToInt().toString())
                    }
                }
                item {
                    StyleSlider(R.string.content_width, draft.contentWidth.toFloat(), 600f..900f, 29) {
                        model.editReading("content_width", it.roundToInt().toString())
                    }
                }
                item {
                    Choices(
                        R.string.alignment,
                        draft.textAlign,
                        listOf("left", "justify"),
                        listOf(R.string.align_left, R.string.align_justify),
                    ) { model.editReading("text_align", it) }
                }
                if (state.readingNoteId != null) {
                    item {
                        TextButton(onClick = {
                            model.saveReading(true)
                        }, enabled = !state.readingSaving) { Text(stringResource(R.string.reset_note_style)) }
                    }
                }
                item { Text(stringResource(R.string.style_online_hint), style = MaterialTheme.typography.bodySmall) }
            }
            Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.End) {
                TextButton(
                    onClick = model::cancelReading,
                    enabled = !state.readingSaving,
                ) { Text(stringResource(R.string.cancel)) }
                Button(onClick = {
                    model.saveReading()
                }, enabled = !state.readingSaving && invalid.isEmpty()) { Text(stringResource(R.string.save)) }
            }
        }
    }
}

@Composable
private fun Choices(
    label: Int,
    selected: String,
    values: List<String>,
    labels: List<Int>,
    change: (String) -> Unit,
) {
    Column {
        Text(stringResource(label), style = MaterialTheme.typography.labelLarge)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            values.forEachIndexed { index, value ->
                FilterChip(
                    selected == value,
                    onClick = { change(value) },
                    label = { Text(stringResource(labels[index])) },
                )
            }
        }
    }
}

@Composable
private fun StyleSlider(
    label: Int,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    steps: Int,
    change: (Float) -> Unit,
) {
    val title = stringResource(label)
    Column {
        Text("$title: ${((value * 10).roundToInt() / 10.0)}")
        Slider(value, change, Modifier.semantics { contentDescription = title }, valueRange = range, steps = steps)
    }
}

@Composable
private fun ColorField(
    label: Int,
    value: String,
    key: String,
    model: MobileModel,
    invalid: (Boolean) -> Unit,
) {
    var text by remember(value) { mutableStateOf(value) }
    val valid = Regex("#[0-9a-fA-F]{6}").matches(text)
    OutlinedTextField(
        text,
        {
            text = it
            val failed = !Regex("#[0-9a-fA-F]{6}").matches(it)
            invalid(failed)
            if (!failed) model.editReading(key, it)
        },
        Modifier.fillMaxWidth(),
        label = { Text(stringResource(label)) },
        singleLine = true,
        isError = !valid,
        supportingText = { if (!valid) Text(stringResource(R.string.color_hint)) },
    )
}
