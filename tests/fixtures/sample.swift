import Foundation
@preconcurrency import RxSwift
import UIKit.UIView
import struct Foundation.Data

public func makeLabel(from raw: String) -> String {
    return decorate(raw)
}

private func decorate(_ value: String) -> String {
    return "[" + value + "]"
}

internal func hidden() {}

public protocol Describable {
    func describe() -> String
}

public class Widget: Describable {
    private var store: Int = 0

    public init(store: Int) {
        self.store = store
    }

    public func describe() -> String {
        return makeLabel(from: "widget")
    }

    public func run(values: [Int]) {
        guard let Foundation = values.first else { return }
        record(Foundation)
        let doubled = values.map { $0 * 2 }
        for value in doubled {
            record(value)
        }
        if let first = doubled.first {
            record(first)
        }
    }

    private func record(_ value: Int) {
        store = value
    }
}

extension Widget {
    public func reset() {
        store = 0
    }
}

actor Counter {
    private var count = 0
}
