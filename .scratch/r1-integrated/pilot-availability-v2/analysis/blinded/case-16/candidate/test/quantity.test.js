import assert from 'node:assert/strict';
import test from 'node:test';
import { lineFromRequest } from '../src/api.js';
import { parseQuantity } from '../src/quantity.js';
import { parseQuantity as parseCliQuantity } from '../src/cli.js';

test('API quantities accept nonnegative integers and reject invalid inputs', () => {
  for (const value of [0, '0']) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity: value }), {
      sku: 'A', quantity: 0, active: false,
    });
  }
  for (const value of [1, 42, '1', ' 42 ']) {
    assert.equal(parseQuantity(value), Number(value));
  }
  for (const value of [-1, '-1', 1.5, '1.5', NaN, Infinity, -Infinity,
    'NaN', 'Infinity', '', '  \t\n', true, false, null, undefined, 'abc']) {
    assert.throws(() => parseQuantity(value), { name: 'Error', message: 'invalid quantity' });
  }
  assert.equal(parseCliQuantity('0'), 1);
});
