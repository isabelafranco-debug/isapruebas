import { argon2Sync, randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';

const {password,salt} = JSON.parse(readFileSync(0,'utf8'));
const nonce = salt ? Buffer.from(salt,'base64') : randomBytes(16);
const key = argon2Sync('argon2id', {
  message:Buffer.from(password,'utf8'),nonce,parallelism:4,memory:65536,passes:3,tagLength:32,
});
console.log('$argon2id$v=19$m=65536,t=3,p=4$'+nonce.toString('base64').replace(/=+$/,'')+'$'+key.toString('base64').replace(/=+$/,''));
