import { test } from 'node:test';
import assert from 'node:assert/strict';
import { lineFromRequest } from '../src/api.js';
import { parseQuantity as parseCliQuantity } from '../src/cli.js';

test('request quantities accept nonnegative integers and reject invalid inputs', () => {
  for (const quantity of [0, '0']) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity }), {
      sku: 'A', quantity: 0, active: false,
    });
  }

  for (const [quantity, expected] of [[1, 1], ['2', 2], [' 3 ', 3]]) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity }), {
      sku: 'A', quantity: expected, active: true,
    });
  }

  for (const quantity of [-1, '-1', 0.5, '0.5', Infinity, -Infinity, NaN, '', ' \t\n', true, false, null, undefined, 'abc']) {
    assert.throws(() => lineFromRequest({ sku: ' A ', quantity }), {
      name: 'Error', message: 'invalid quantity',
    });
  }

  assert.equal(parseCliQuantity('0'), 1);
  assert.equal(parseCliQuantity('5abc'), 5);
});
