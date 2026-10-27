import { handle as mail } from './channels/mail.js';
import { handle as audit } from './channels/audit.js';
export const registry = Object.assign(Object.create(null), { mail, audit });
