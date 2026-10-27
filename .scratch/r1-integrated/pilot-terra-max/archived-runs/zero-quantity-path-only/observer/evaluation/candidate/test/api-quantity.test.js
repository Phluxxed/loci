import assert from 'node:assert/strict';
import test from 'node:test';
import { lineFromRequest } from '../src/api.js';

test('request quantities accept zero and positive integers, and reject invalid inputs', () => {
  for (const quantity of [0, '0']) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity }), {
      sku: 'A', quantity: 0, active: false,
    });
  }

  for (const quantity of [1, 42, '1', ' 42 ']) {
    assert.deepEqual(lineFromRequest({ sku: ' A ', quantity }), {
      sku: 'A', quantity: Number(quantity), active: true,
    });
  }

  for (const quantity of [
    -1, '-1', 0.5, '0.5', Infinity, -Infinity, NaN, 'Infinity',
    '', ' ', '\t\n', true, false, null, undefined, 'not a number',
  ]) {
    assert.throws(() => lineFromRequest({ sku: 'A', quantity }), {
      name: 'Error', message: 'invalid quantity',
    });
  }
});
