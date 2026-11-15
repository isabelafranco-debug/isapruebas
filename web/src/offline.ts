const worker='/regional/offline-sw.js';
export const OFFLINE_MAP='/mapa-sin-conexion';

export async function downloadMap() {
  if(!('serviceWorker' in navigator)||!window.isSecureContext)throw new Error('La descarga del mapa necesita HTTPS y un navegador compatible.');
  await navigator.serviceWorker.register(worker,{scope:'/',updateViaCache:'none'});
  const registration=await navigator.serviceWorker.ready;
  await new Promise<void>((resolve,reject)=>{
    const port=new MessageChannel();
    const timer=window.setTimeout(()=>{
      port.port1.close();reject(new Error('La descarga tardó demasiado. Reintenta con conexión.'));
    },90000);
    port.port1.onmessage=e=>{
      clearTimeout(timer);port.port1.close();
      if(e.data?.ready)resolve();else reject(new Error('No se pudo guardar el mapa. Revisa la conexión o el espacio disponible.'));
    };
    registration.active!.postMessage('download-regional-map',[port.port2]);
  });
}
