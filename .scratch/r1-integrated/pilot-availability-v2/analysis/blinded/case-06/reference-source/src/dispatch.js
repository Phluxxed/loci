import { registry } from './registry.js';
export function dispatch(event) {
  const handler = registry[event.kind];
  if (!handler) throw new Error('unknown kind');
  return handler(event.payload);
}
