import { readdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

export const regionalMapPackage={name:'regional-map-package',apply:'build',async closeBundle(){
  const files=['/mapa-sin-conexion','/favicon.svg','/regional/places.json','/regional/santa-cruz.geojson',
    ...(await readdir('dist/assets')).map(file=>'/assets/'+file)];
  const hash=createHash('sha256');
  for(const path of files)hash.update(await readFile(path==='/mapa-sin-conexion'?'dist/index.html':'dist'+path));
  const source=await readFile('offline-sw.js','utf8');
  hash.update(source);
  await writeFile('dist/regional/offline-sw.js',source.replace('BUILD_ID',JSON.stringify(hash.digest('hex').slice(0,16)))
    .replace('OFFLINE_ASSETS',JSON.stringify(files)));
}};
