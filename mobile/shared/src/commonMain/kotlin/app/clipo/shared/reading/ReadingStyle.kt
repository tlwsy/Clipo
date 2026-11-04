package app.clipo.shared.reading

import app.clipo.shared.api.wireJson
import app.clipo.shared.model.generated.ReadingPreferences
import app.clipo.shared.model.generated.ReadingStylePatch
import com.materialkolor.hct.Hct
import com.materialkolor.palettes.TonalPalette
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonObject

/** Shared web-compatible presets, merge rules and HCT tones. No platform UI types. */
object ReadingStyle {
    fun preset(theme: String): ReadingPreferences =
        when (theme) {
            "compact" -> base(theme, 16, 1.4, 12, 680, "left", "#ffffff", "#0a0a0a")
            "focus" -> base(theme, 20, 1.8, 20, 600, "left", "#1c1917", "#fafafa")
            "print" -> base(theme, 16, 1.5, 12, 900, "justify", "#ffffff", "#000000")
            else -> base("comfortable", 18, 1.6, 16, 720, "left", "#fefce8", "#1c1917")
        }

    private fun base(
        theme: String,
        size: Long,
        line: Double,
        spacing: Long,
        width: Long,
        align: String,
        background: String,
        text: String,
    ): ReadingPreferences =
        ReadingPreferences(theme, "system-ui", size, 400, line, spacing, width, align, background, text)

    fun resolve(
        global: ReadingPreferences?,
        overrides: ReadingStylePatch?,
    ): ReadingPreferences {
        val base = overrides?.theme?.let(::preset) ?: global ?: preset("comfortable")
        if (overrides == null) return base
        val fields = wireJson.encodeToJsonElement(base).jsonObject.toMutableMap()
        fields.putAll(wireJson.encodeToJsonElement(overrides).jsonObject.filterValues { it != JsonNull })
        return wireJson.decodeFromJsonElement(JsonObject(fields))
    }

    /** Invalid intermediate text stays in the platform editor, never enters the shared draft. */
    fun edit(
        style: ReadingPreferences,
        key: String,
        value: String,
    ): ReadingPreferences? {
        if (key == "theme") return preset(value).takeIf { value in listOf("comfortable", "compact", "focus", "print") }
        val numeric =
            mapOf(
                "font_size" to 14.0..24.0,
                "font_weight" to 400.0..700.0,
                "line_height" to 1.2..2.0,
                "paragraph_spacing" to 0.0..40.0,
                "content_width" to 600.0..900.0,
            )
        val choices =
            mapOf(
                "font_family" to listOf("system-ui", "serif", "sans-serif", "online"),
                "text_align" to listOf("left", "justify"),
                "color_mode" to listOf("custom", "system", "monet"),
                "monet_scheme" to listOf("light", "dark", "system"),
            )
        val field =
            when {
                key in numeric -> {
                    val number = value.toDoubleOrNull() ?: return null
                    if (number !in numeric.getValue(key)) return null
                    if (key == "font_weight" && number !in listOf(400.0, 500.0, 600.0, 700.0)) return null
                    if (key != "line_height" && number % 1 != 0.0) return null
                    if (key == "line_height") JsonPrimitive(number) else JsonPrimitive(number.toLong())
                }
                key in choices -> if (value in choices.getValue(key)) JsonPrimitive(value) else return null
                key in listOf("background_color", "text_color", "monet_seed") ->
                    if (Regex("#[0-9a-fA-F]{6}").matches(value)) JsonPrimitive(value.lowercase()) else return null
                else -> return null
            }
        val fields = wireJson.encodeToJsonElement(style).jsonObject.toMutableMap()
        fields[key] = field
        return wireJson.decodeFromJsonElement(JsonObject(fields))
    }

    fun json(style: ReadingPreferences): String = wireJson.encodeToString(style)

    fun colors(
        style: ReadingPreferences,
        systemDark: Boolean,
    ): ReadingColors {
        if (style.colorMode == "system") {
            return if (systemDark) {
                ReadingColors("#202421", "#e6e9e2", "#a2d6bd", true)
            } else {
                ReadingColors("#fafbf7", "#242925", "#226552", false)
            }
        }
        if (style.colorMode == "monet") {
            val source = Hct.fromInt(argb(style.monetSeed))
            val neutral = TonalPalette.fromHueAndChroma(source.hue, 12.0)
            val primary = TonalPalette.fromHueAndChroma(source.hue, source.chroma.coerceIn(24.0, 48.0))
            val dark = style.monetScheme == "dark" || (style.monetScheme != "light" && systemDark)
            return ReadingColors(
                hex(neutral.tone(if (dark) 12 else 96)),
                hex(neutral.tone(if (dark) 90 else 15)),
                hex(primary.tone(if (dark) 80 else 35)),
                dark,
            )
        }
        val color = argb(style.backgroundColor)
        val dark = ((color shr 16) and 255) * 0.299 + ((color shr 8) and 255) * 0.587 + (color and 255) * 0.114 < 140
        return ReadingColors(style.backgroundColor, style.textColor, if (dark) "#a2d6bd" else "#226552", dark)
    }

    private fun argb(hex: String): Int = (hex.removePrefix("#").toLong(16) or 0xff000000).toInt()

    private fun hex(color: Int): String = "#" + (color and 0xffffff).toString(16).padStart(6, '0')
}

data class ReadingColors(
    val background: String,
    val text: String,
    val accent: String,
    val dark: Boolean,
)
