import type { User } from './types';

export class ApiError extends Error {
  constructor(message:string, public status:number) { super(message); }
}

let csrf = '';
export function session(user:User|null) { csrf = user?.csrf ?? ''; }
export async function api<T>(path:string, opts:RequestInit = {}):Promise<T> {
  const headers = new Headers(opts.headers);
  if (opts.body && !(opts.body instanceof FormData)) headers.set('Content-Type','application/json');
  if (opts.method && opts.method !== 'GET' && csrf) headers.set('X-CSRF-Token',csrf);
  let response:Response;
  const timeout=new AbortController();
  const timer=window.setTimeout(()=>timeout.abort(),90000);
  try { response = await fetch('/api'+path,{...opts,headers,signal:opts.signal??timeout.signal}); }
  catch (err) {
    if (opts.signal?.aborted) throw err;
    throw new Error('La conexión tardó demasiado o se interrumpió. Espera un momento y vuelve a intentar.');
  } finally {clearTimeout(timer);}
  if (!response.ok) {
    const result = await response.json().catch(()=>({}));
    throw new ApiError(typeof result.detail === 'string' ? result.detail : response.status>=500?
      'El servicio se está iniciando o está temporalmente ocupado. Vuelve a intentar en un momento.':'No pudimos completar la solicitud.',response.status);
  }
  return (response.status===204 ? undefined : await response.json()) as T;
}
export function post<T>(path:string, data?:unknown) {
  return api<T>(path,{method:'POST',body:data === undefined ? undefined : JSON.stringify(data)});
}
export function errorText(err:unknown) { return err instanceof Error ? err.message : 'Vuelve a intentar.'; }
export const n = (value:number|null|undefined, decimals=0) => value == null ? '—' : new Intl.NumberFormat('es-BO',{maximumFractionDigits:decimals}).format(value);
export const day = (value:string) => new Intl.DateTimeFormat('es-BO',{dateStyle:'medium',timeZone:'America/La_Paz'}).format(new Date(value));
