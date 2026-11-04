import XCTest
@testable import Clipo

final class ClipoTests: XCTestCase {
    func testKeychainRoundTripAndRemoval() {
        let store = KeychainTokenStore()
        XCTAssertTrue(store.clear())
        defer { _ = store.clear() }
        XCTAssertTrue(store.write(value: "test-refresh-only"))
        XCTAssertEqual(store.read(), "test-refresh-only")
        XCTAssertTrue(store.write(value: "rotated-test-refresh"))
        XCTAssertEqual(store.read(), "rotated-test-refresh")
        XCTAssertTrue(store.clear())
        XCTAssertNil(store.read())
    }
}
