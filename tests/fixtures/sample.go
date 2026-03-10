// Package sample provides example code for testing.
package sample

import "fmt"

// Greet returns a greeting string for the given name.
func Greet(name string) string {
	return fmt.Sprintf("Hello, %s!", name)
}

// helper is a private utility — also a symbol, Go has no lambda-const idiom.
func helper(x int) int {
	return x * 2
}

// Calculator holds state for arithmetic operations.
type Calculator struct {
	value float64
}

// Add adds x to the calculator's running total.
func (c *Calculator) Add(x float64) float64 {
	c.value += x
	return c.value
}

// Reset resets the calculator's value to zero.
func (c *Calculator) Reset() {
	c.value = 0
}

// Shape is an interface for geometric shapes.
type Shape interface {
	Area() float64
	Perimeter() float64
}

// Vector is a named type for a slice of floats.
type Vector []float64

// PI is a constant — should NOT be extracted as a symbol.
const PI = 3.14159
