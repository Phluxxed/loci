//! Sample Rust module for testing.

/// Adds two integers together.
pub fn add(x: i32, y: i32) -> i32 {
    x + y
}

/// A simple counter struct.
pub struct Counter {
    count: u32,
}

impl Counter {
    /// Creates a new Counter starting at zero.
    pub fn new() -> Self {
        Counter { count: 0 }
    }

    /// Increments the counter by one.
    pub fn increment(&mut self) {
        self.count += 1;
    }

    /// Returns the current count.
    pub fn value(&self) -> u32 {
        self.count
    }
}

/// A trait for types that can describe themselves.
pub trait Describable {
    fn describe(&self) -> String;
}

/// Primary color variants.
pub enum Color {
    Red,
    Green,
    Blue,
}

// MAX_COUNT is a constant — should NOT be extracted as a symbol.
const MAX_COUNT: u32 = 100;
