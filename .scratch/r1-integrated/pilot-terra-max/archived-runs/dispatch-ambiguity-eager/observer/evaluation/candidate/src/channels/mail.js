import { encode } from '../codec.js';
export function handle(value) { return `mail:${encode(value)}`; }
