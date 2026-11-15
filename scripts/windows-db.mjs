import { PGlite } from '@electric-sql/pglite';
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';
import { postgis } from '@electric-sql/pglite-postgis';

const db = await PGlite.create(process.env.JUPITER_PGLITE_DATA || 'pgdata',{extensions:{postgis}});
const server = new PGLiteSocketServer({db,host:'127.0.0.1',port:Number(process.env.JUPITER_PGLITE_PORT||55433),maxConnections:20});
await server.start();
console.log('Base de desarrollo local iniciada en loopback.');
