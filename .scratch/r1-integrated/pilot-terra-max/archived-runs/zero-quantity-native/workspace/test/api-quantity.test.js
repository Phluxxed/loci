import assert from 'node:assert/strict';
import test from 'node:test';
import { lineFromRequest } from '../src/api.js';
import { parseQuantity as parseCliQuantity } from '../src/cli.js';

test('request quantities accept nonnegative integers and reject invalid inputs', () => {
  for (const quantity of [0, '0']) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity }), {
      sku: 'A', quantity: 0, active: false,
    });
  }

  for (const [quantity, expected] of [[1, 1], ['1', 1], [42, 42], [' 42 ', 42], ['1e2', 100]]) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity }), {
      sku: 'A', quantity: expected, active: true,
    });
  }

  for (const quantity of [
    -1, '-1', 0.5, '0.5', -0.5, '-0.5', Infinity, -Infinity, NaN,
    'Infinity', 'NaN', '', ' ', '\t\n', '\u00a0', true, false, null, undefined, 'abc',
  ]) {
    assert.throws(() => lineFromRequest({ sku: 'A', quantity }), {
      name: 'Error', message: 'invalid quantity',
    }, `quantity: ${String(quantity)}`);
  }

  assert.equal(parseCliQuantity(0), 1);
  assert.equal(parseCliQuantity('0'), 1);
});
