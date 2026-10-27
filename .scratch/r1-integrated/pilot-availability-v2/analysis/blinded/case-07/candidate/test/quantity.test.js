import assert from 'node:assert/strict';
import { test } from 'node:test';
import { lineFromRequest } from '../src/api.js';
import { parseQuantity as parseCliQuantity } from '../src/cli.js';

test('request quantities accept nonnegative integers and reject invalid inputs', () => {
  for (const quantity of [0, '0']) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity }), {
      sku: 'A', quantity: 0, active: false,
    });
  }

  for (const quantity of [1, 12, '1', ' 12 ', '1e2']) {
    const line = lineFromRequest({ sku: 'A', quantity });
    assert.equal(line.quantity, Number(quantity));
    assert.equal(line.active, true);
  }

  for (const quantity of [-1, '-1', 0.5, '0.5', NaN, Infinity, -Infinity,
    '', '   ', '\t\n', true, false, null, undefined, 'abc']) {
    assert.throws(() => lineFromRequest({ sku: 'A', quantity }), {
      name: 'Error', message: 'invalid quantity',
    });
  }

  assert.equal(parseCliQuantity('0'), 1);
});
