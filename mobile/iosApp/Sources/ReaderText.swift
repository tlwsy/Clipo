import ClipoShared
import CoreText
import SwiftUI
import UIKit

extension UIColor {
    convenience init(readingHex: String) {
        let value = UInt32(readingHex.dropFirst(), radix: 16) ?? 0
        self.init(red: CGFloat((value >> 16) & 255) / 255,
                  green: CGFloat((value >> 8) & 255) / 255,
                  blue: CGFloat(value & 255) / 255, alpha: 1)
    }
}

/// UITextView preserves UTF-16 ranges and the platform selection menu for the M2 annotation work.
struct ReaderText: UIViewRepresentable {
    let block: ReaderBlock
    let style: ReadingPreferences
    let colors: ReadingColors
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false
        view.isSelectable = true
        view.isScrollEnabled = false
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        _ = dynamicTypeSize
        let text = Self.attributed(block: block, style: style, colors: colors)
        if view.attributedText != text { view.attributedText = text }
        view.linkTextAttributes = [.foregroundColor: UIColor(readingHex: colors.accent), .underlineStyle: 1]
        if block.kind == "heading" { view.accessibilityTraits.insert(.header) }
        else { view.accessibilityTraits.remove(.header) }
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    static func font(style: ReadingPreferences, bold: Bool = false, italic: Bool = false,
                     code: Bool = false, scale: Double = 1) -> UIFont {
        let size = CGFloat(Double(style.fontSize) * scale)
        let weightValue = bold ? 700 : Int(style.fontWeight)
        let weight: UIFont.Weight = [400: .regular, 500: .medium, 600: .semibold, 700: .bold][weightValue] ?? .regular
        var font = code ? UIFont.monospacedSystemFont(ofSize: size, weight: weight) : UIFont.systemFont(ofSize: size, weight: weight)
        if !code && style.fontFamily == "serif", let descriptor = font.fontDescriptor.withDesign(.serif) {
            font = UIFont(descriptor: descriptor, size: size)
        }
        if !code && style.fontFamily == "online" {
            let serif = style.onlineFont?.family.localizedCaseInsensitiveContains("Serif") == true
            let name = serif ? "ClipoReadingSerif" : "ClipoReadingSans"
            if let bundled = UIFont(name: name, size: size) {
                let descriptor = bundled.fontDescriptor.addingAttributes([
                    UIFontDescriptor.AttributeName(rawValue: kCTFontVariationAttribute as String): [NSNumber(value: 0x77676874): NSNumber(value: weightValue)]
                ])
                font = UIFont(descriptor: descriptor, size: size)
            }
        }
        if italic, let descriptor = font.fontDescriptor.withSymbolicTraits(font.fontDescriptor.symbolicTraits.union(.traitItalic)) {
            font = UIFont(descriptor: descriptor, size: size)
        }
        return UIFontMetrics(forTextStyle: .body).scaledFont(for: font)
    }

    static func attributed(block: ReaderBlock, style: ReadingPreferences, colors: ReadingColors) -> NSAttributedString {
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineHeightMultiple = CGFloat(style.lineHeight)
        paragraph.alignment = style.textAlign == "justify" && block.kind != "code" ? .justified : .natural
        let heading = block.kind == "heading"
        let scale = heading ? 1.65 - Double(block.level) * 0.1 : 1
        func attributes(bold: Bool = false, italic: Bool = false, code: Bool = false) -> [NSAttributedString.Key: Any] {
            [.font: font(style: style, bold: heading || block.header || bold, italic: italic,
                         code: block.kind == "code" || code, scale: scale),
             .foregroundColor: UIColor(readingHex: colors.text), .paragraphStyle: paragraph]
        }
        let result = NSMutableAttributedString(string: block.prefix, attributes: attributes())
        if block.inlines.isEmpty || block.kind == "code" {
            result.append(NSAttributedString(string: block.text, attributes: attributes()))
        } else {
            for inline in block.inlines {
                var attrs = attributes(bold: inline.bold, italic: inline.italic, code: inline.code)
                if inline.strike { attrs[.strikethroughStyle] = NSUnderlineStyle.single.rawValue }
                if let safe = ReaderDocument.shared.safeUrl(value: inline.url), let url = URL(string: safe) { attrs[.link] = url }
                result.append(NSAttributedString(string: inline.text, attributes: attrs))
            }
        }
        return result
    }
}
