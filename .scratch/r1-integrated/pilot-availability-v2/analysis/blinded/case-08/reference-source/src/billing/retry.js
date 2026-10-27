export function retryDelay(attempt) { return Math.min(1000 * 2 ** attempt, 8000); }
