import ClipoShared
import SwiftUI
import XCTest
@testable import Clipo

@MainActor
final class ReaderTests: XCTestCase {
    func testNativeRangesAndSafeRichText() throws {
        let style = ReadingStyle.shared.preset(theme: "comfortable")
        let colors = ReadingStyle.shared.colors(style: style, systemDark: false)
        let block = try XCTUnwrap(ReaderDocument.shared.markdown(source: "中文😀 **bold** [link](https://example.com)").first)
        let text = ReaderText.attributed(block: block, style: style, colors: colors)
        XCTAssertEqual((text.string as NSString).substring(with: NSRange(location: 0, length: 4)), "中文😀")
        XCTAssertEqual(text.length, (text.string as NSString).length)
        let link = (text.string as NSString).range(of: "link")
        XCTAssertEqual(text.attribute(.link, at: link.location, effectiveRange: nil) as? URL, URL(string: "https://example.com"))
        let unsafe = try XCTUnwrap(ReaderDocument.shared.markdown(source: "[bad](javascript:alert)").first)
        XCTAssertNil(ReaderText.attributed(block: unsafe, style: style, colors: colors).attribute(.link, at: 0, effectiveRange: nil))
    }

    func testBundledFontsAndFourWeights() throws {
        XCTAssertNotNil(UIFont(name: "ClipoReadingSans", size: 18))
        XCTAssertNotNil(UIFont(name: "ClipoReadingSerif", size: 18))
        let base = try XCTUnwrap(ReadingStyle.shared.edit(
            style: ReadingStyle.shared.preset(theme: "comfortable"), key: "font_family", value: "online"))
        var amounts: [Int] = []
        for weight in [400, 500, 600, 700] {
            let style = try XCTUnwrap(ReadingStyle.shared.edit(style: base, key: "font_weight", value: String(weight)))
            let font = ReaderText.font(style: style)
            XCTAssertTrue(font.familyName.contains("Clipo Reading"))
            amounts.append(try ink(font))
        }
        for pair in zip(amounts, amounts.dropFirst()) { XCTAssertGreaterThan(pair.1, pair.0) }
    }

    private func ink(_ font: UIFont) throws -> Int {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let image = UIGraphicsImageRenderer(size: CGSize(width: 300, height: 90), format: format).image { context in
            UIColor.white.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 300, height: 90))
            ("中文阅读 Aa" as NSString).draw(at: CGPoint(x: 4, y: 4), withAttributes: [.font: font, .foregroundColor: UIColor.black])
        }
        let bytes = try XCTUnwrap(image.cgImage?.dataProvider?.data) as Data
        return bytes.reduce(0) { $0 + 255 - Int($1) }
    }

    func testNativeReaderSizingAndSnapshot() throws {
        let style = ReadingStyle.shared.preset(theme: "comfortable")
        let colors = ReadingStyle.shared.colors(style: style, systemDark: false)
        let block = try XCTUnwrap(ReaderDocument.shared.markdown(source: "## 中文😀阅读\n\n**Bold** and italic").first)
        let view = UITextView()
        view.isScrollEnabled = false
        view.attributedText = ReaderText.attributed(block: block, style: style, colors: colors)
        let size = view.sizeThatFits(CGSize(width: 320, height: 10000))
        XCTAssertGreaterThan(size.height, 20)
        XCTAssertLessThan(size.height, 200)
        let normal = ReaderText.font(style: style, category: .large)
        let large = ReaderText.font(style: style, category: .accessibilityExtraLarge)
        XCTAssertGreaterThan(large.pointSize, normal.pointSize * 1.5)
        for (name, width, height, large) in [("phone", 390, 844, false), ("tablet", 1024, 768, false),
                                            ("large-text", 390, 844, true)] {
            let root = ReaderPage(note: fixture(), style: style)
                .environment(\.dynamicTypeSize, large ? .accessibility3 : .large)
            let host = UIHostingController(rootView: root)
            let window = UIWindow(frame: CGRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)))
            window.rootViewController = host
            window.makeKeyAndVisible()
            host.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(size: window.bounds.size).image { _ in
                window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
            }
            let attachment = XCTAttachment(image: image)
            attachment.name = "M1-reader-\(name)"
            attachment.lifetime = .keepAlways
            add(attachment)
            window.isHidden = true
        }
    }

    private func fixture() -> NoteResponse {
        let content = CapturedContent(
            url: "https://example.com/mobile", platform: "web", siteName: "Clipo", title: "Mobile acceptance",
            text: "中文😀内容\n\nOffline reading.", author: "Clipo", authorUrl: nil, publishedAt: nil,
            images: [], blocks: [block("text", "中文😀内容"), block("text", "Offline reading."),
                                block("heading", "Rich heading"), block("quote", "Quoted sample"),
                                block("code", "val emoji = \"中文😀\""),
                                block("list", "", children: [block("list_item", "First item"), block("list_item", "Second item")]),
                                block("table", "", children: [block("table_row", "", children: [
                                    block("table_cell", "Column A"), block("table_cell", "Column B")])]),
                                block("details", "More details", children: [block("text", "Hidden paragraph")])],
            contentVersion: 1, comments: [], commentCaptureLimit: nil, captureWarnings: [], extractorVersion: 0, rawHtml: nil, selection: nil)
        return NoteResponse(
            id: 1, title: content.title, url: content.url,
            source: SourceResponse(platform: "web", siteName: "Clipo", originUrl: content.url,
                                   author: "Clipo", authorUrl: nil, publishedAt: nil),
            content: content, annotations: [], readingPreferences: nil, displayOverrides: nil, comments: [],
            summaryMarkdown: "## Summary heading\n\n**Bold summary** with `code`.", keyPoints: ["Key point"],
            suggestedTags: [], tags: [], isFavorite: false, status: "ready", summaryError: nil,
            commentInsights: [], commentScoreError: nil, createdAt: "2026-11-04", updatedAt: "2026-11-04")
    }

    private func block(_ kind: String, _ text: String, children: [CapturedBlockOutput] = []) -> CapturedBlockOutput {
        CapturedBlockOutput(type: kind, text: text, inlines: [], children: children, url: nil, image: nil,
                            alt: "", level: 2, ordered: true, header: false, width: nil, height: nil, appid: nil, store: nil)
    }
}
