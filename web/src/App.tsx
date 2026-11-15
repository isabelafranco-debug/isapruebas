import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react';
import { Activity, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, ChevronDown, CloudSun, FileText, Globe2,
  LayoutDashboard, Leaf, LogOut, MapPin, Menu, Plus, Sprout, X } from 'lucide-react';
import { api,day,errorText,n,post,session,ApiError } from './client';
import type { Report, RunSummary, Site, User } from './types';
import { FieldEditor } from './FieldEditor';
import { Compare } from './Compare';
import { OFFLINE_MAP } from './offline';
import { GuidedTour } from './GuidedTour';

const RegionalMap=lazy(()=>import('./Map'));

function OfflineMap(){
  return <main className="main offline-page"><Brand/><h1>Mapa sin conexión de Santa Cruz</h1>
    <p>Límites de provincias y referencias municipales. Busca un lugar, consulta coordenadas o dibuja para orientarte.</p>
    <p className="muted">Para guardar lotes, consultar suelo o ejecutar análisis, vuelve al <a href="/">panel en línea</a>.</p>
    <Suspense fallback={<p>Cargando mapa…</p>}><RegionalMap initial={null} offline onShape={()=>{}}/></Suspense>
  </main>;
}

function useLocation() {
  const [path,setPath] = useState(window.location.pathname);
  useEffect(()=>{const handler=()=>setPath(window.location.pathname);window.addEventListener('popstate',handler);
    return ()=>window.removeEventListener('popstate',handler);},[]);
  function go(next:string) { if (path!==next) {window.history.pushState({},'',next);setPath(next);window.scrollTo(0,0);} }
  return {path,go};
}
export type Go = (path:string)=>void;
const navigation = [
  {name:'Panel',path:'/',Icon:LayoutDashboard},
  {name:'Mis lotes',path:'/lotes',Icon:MapPin},
  {name:'Comparar rotaciones',path:'/comparar',Icon:Activity},
  {name:'Informes',path:'/informes',Icon:FileText},
];

function Brand() {return <div className="brand"><img src="/favicon.svg" alt="" width="42" height="42"/><div><b>Júpiter Jr</b><small>Planificación agrícola</small></div></div>}

function Access({onLogin}:{onLogin:(u:User)=>void}) {
  const [create,setCreate]=useState(false), [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();const fields=Object.fromEntries(new FormData(event.currentTarget));setBusy(true);setError('');
    try {onLogin(await post<User>('/auth/'+(create?'register':'login'),fields));}
    catch(err){setError(errorText(err));} finally{setBusy(false);}
  }
  return <main className="access"><aside className="access-photo"><Brand/><div><span className="eyebrow light"><span/> NASA POWER · AGRICULTURA</span>
    <h1>El clima cambia.<br/>Tu rotación puede<br/>adaptarse.</h1><p>Explora cómo responderían tus cultivos con el clima histórico de tu zona.</p>
    </div><p className="image-credit">Imagen ilustrativa del paisaje agrícola</p></aside>
    <section className="access-body"><div className="mobile-brand"><Brand/></div><div className="access-form"><span className="eyebrow"><span/> TU ESPACIO DE TRABAJO</span>
      <h2>{create?'Crea tu cuenta':'Bienvenido a Júpiter Jr'}</h2>
      <p>{create?'Registra tu cuenta para explorar el lote piloto o agregar tu propio terreno.':'Inicia sesión para ver tus lotes y análisis.'}</p>
      <form onSubmit={submit}>
        {create&&<label>Nombre visible<input name="name" autoComplete="name" required minLength={2} maxLength={100} placeholder="Tu nombre"/></label>}
        <label>Correo electrónico<input name="email" type="email" autoComplete="email" required placeholder="nombre@correo.com"/></label>
        <label>Contraseña<input name="password" type="password" autoComplete={create?'new-password':'current-password'} required minLength={10} maxLength={128} placeholder="Al menos 10 caracteres"/></label>
        {error&&<p className="error" role="alert">{error}</p>}
        <button className="button primary" disabled={busy}>{busy?'Conectando…':create?'Crear cuenta':'Iniciar sesión'} <ArrowRight size={17}/></button>
      </form>
      <div className="access-switch">{create?'¿Ya tienes cuenta?':'¿Primera vez aquí?'} <button onClick={()=>{setCreate(!create);setError('');}}>{create?'Inicia sesión':'Crear cuenta'}</button></div>
    </div></section></main>;
}

function Dashboard({user,sites,runs,reports,go}:{user:User;sites:Site[];runs:RunSummary[];reports:Report[];go:Go}) {
  const pilot=sites.find(x=>x.pilot);
  const ready=runs.filter(r=>r.status==='done');
  return <>
    <section className="hero" data-tour="dashboard">
      <div className="hero-content"><span className="eyebrow light"><span/> PLANIFICACIÓN DE CULTIVOS</span>
        <h1>Planifica tu próxima<br/>rotación</h1>
        <p>Ubica tu lote, compara tres campañas con clima histórico y lleva la evidencia a tu próxima decisión.</p>
        <button className="button lime" onClick={()=>go(pilot?'/lotes/'+pilot.id:'/lotes/nuevo')}>{pilot?'Explorar lote piloto':'Crear un lote'} <ArrowRight size={18}/></button>
      </div>
      <div className="hero-meta"><Globe2 size={15}/> Imagen ilustrativa · Bolivia</div>
    </section>
    <div className="metrics">
      {[
        {Icon:MapPin,title:'Lotes guardados',value:sites.length,sub:'Abre el mapa y edita tus límites',path:'/lotes'},
        {Icon:Activity,title:'Análisis terminados',value:ready.length,sub:'Historial de tus comparaciones',path:'/comparar'},
        {Icon:FileText,title:'Informes listos',value:reports.filter(r=>r.ready).length,sub:'Descargas en PDF y CSV',path:'/informes'}
      ].map(({Icon,title,value,sub,path})=><button className="metric card" key={title} onClick={()=>go(path)}><span className="metric-icon"><Icon size={19}/></span><ArrowUpRight className="metric-arrow" size={17}/><span className="metric-label">{title}</span><strong>{value}</strong><span className="muted">{sub}</span></button>)}
    </div>
    <div className="dashboard-bottom">
      <section className="card panel"><div className="section-head"><div><h2>Tus lotes</h2><p>Terrenos que puedes abrir y analizar.</p></div><button className="button secondary small" onClick={()=>go('/lotes/nuevo')}><Plus size={16}/> Nuevo lote</button></div>
        {sites.length ? sites.slice(0,3).map(s=><SiteRow site={s} go={go} key={s.id}/>) : <p className="muted">Agrega un punto o dibuja un terreno para comenzar.</p>}
      </section>
      <section className="card panel mission"><div className="mission-icon"><CloudSun size={23}/></div><h2>Clima de referencia</h2>
        <p>El punto piloto usa el histórico diario de NASA POWER de 2015 a 2025. Consulta sus unidades y cobertura en cada análisis.</p>
        {pilot&&<button className="text-button" onClick={()=>go('/lotes/'+pilot.id+'/analizar')}>Preparar análisis <ArrowRight size={16}/></button>}
      </section>
    </div>
    {ready.length>0&&<section className="card panel"><div className="section-head"><div><h2>Último análisis</h2><p>{ready[0].field_name} · {day(ready[0].created)}</p></div><button className="button secondary" onClick={()=>go('/comparar/'+ready[0].id)}>Ver resultados <ArrowRight size={16}/></button></div></section>}
  </>;
}

function SiteRow({site,go}:{site:Site;go:Go}) {
  return <button className="site-row" onClick={()=>go('/lotes/'+site.id)}>
    <span className="site-icon"><MapPin size={19}/></span><span className="site-name"><b>{site.name}</b><small>{site.lat.toFixed(5)}°, {site.lon.toFixed(5)}° · {site.area_ha===null?'Punto exploratorio':n(site.area_ha,2)+' ha'}</small></span>
    {site.pilot&&<span className="chip">Piloto</span>}<ArrowRight className="site-arrow" size={17}/></button>;
}

export function App(){return window.location.pathname===OFFLINE_MAP?<OfflineMap/>:<Workspace/>;}

function Workspace() {
  const {path,go}=useLocation();
  const [user,setUser]=useState<User|null>(),[initialError,setInitialError]=useState('');
  const [sites,setSites]=useState<Site[]>([]),[runs,setRuns]=useState<RunSummary[]>([]),[reports,setReports]=useState<Report[]>([]);
  const [error,setError]=useState(''),[menu,setMenu]=useState(false),[profile,setProfile]=useState(false);
  const [showGuide,setShowGuide]=useState(false);
  const guideClaim=useRef('');
  const [slow,setSlow]=useState(false);
  function signed(u:User|null){session(u);setUser(u);}
  function loadUser(){setInitialError('');void api<User>('/me').then(signed).catch(err=>{
    if(err instanceof ApiError&&err.status===401)signed(null);else setInitialError(errorText(err));});}
  useEffect(loadUser,[]);
  useEffect(()=>{const timer=window.setTimeout(()=>setSlow(true),12000);return ()=>clearTimeout(timer);},[]);
  useEffect(()=>{
    if(!user||user.guide_seen||guideClaim.current===user.id)return;
    guideClaim.current=user.id;
    void post<{show:boolean}>('/me/guide/start').then(result=>{
      setUser(current=>current?.id===user.id?{...current,guide_seen:true}:current);
      if(result.show){go('/');setShowGuide(true);}
    }).catch(err=>{guideClaim.current='';setError(errorText(err));});
  },[user]);
  async function refresh(){
    try {
      const [s,a,r]=await Promise.all([api<Site[]>('/fields'),api<RunSummary[]>('/analyses'),api<Report[]>('/reports')]);
      setSites(s);setRuns(a);setReports(r);setError('');
    }catch(err){if(err instanceof ApiError&&err.status===401)signed(null);else setError(errorText(err));}
  }
  useEffect(()=>{if(user)void refresh();},[user,path]);
  useEffect(()=>{
    if(!user||![...runs,...reports].some(x=>x.status==='queued'||x.status==='running'))return;
    const timer=window.setInterval(()=>void refresh(),3500);
    return ()=>clearInterval(timer);
  },[user,runs,reports]);

  if(initialError) return <main className="empty app-empty"><Sprout size={31}/><h1>Abriendo Júpiter Jr</h1><p>{initialError}</p><button className="button primary" onClick={loadUser}>Reintentar</button></main>;
  if(user===undefined)return <main className="empty app-empty"><Sprout size={31}/><h1>Conectando con Júpiter Jr</h1>
    <p>{slow?'El alojamiento gratuito puede tardar alrededor de un minuto en activarse después de una pausa.':'Abriendo tu espacio de planificación…'}</p>
    {slow&&<button className="button secondary" onClick={loadUser}>Reintentar conexión</button>}</main>;
  if(user===null)return <Access onLogin={u=>{signed(u);go('/');}}/>;
  const parts=path.split('/').filter(Boolean);
  const section=parts[0]??'';
  const title=navigation.find(x=>x.path===(section?'/'+section:'/'))?.name??'Panel';
  const route=(url:string)=>{go(url);setMenu(false);setProfile(false);};
  const firstName=user.name.split(' ')[0];
  async function close(){try{await post('/auth/logout');signed(null);setProfile(false);go('/');}catch(err){setError(errorText(err));}}
  return <div className="shell">
    {menu&&<button className="overlay" aria-label="Cerrar menú" onClick={()=>setMenu(false)}/>}
    <aside className={'sidebar '+(menu?'open':'')}>
      <button className="brand-button" onClick={()=>route('/')}><Brand/></button>
      <div className="nav-label">ESPACIO DE TRABAJO</div>
      <nav data-tour="navigation" aria-label="Navegación principal">{navigation.map(({name,path:url,Icon})=>{
        const active=url==='/'?path==='/':path.startsWith(url);
        return <button key={url} aria-current={active?'page':undefined} className={active?'active':''} onClick={()=>route(url)}><Icon size={18}/><span>{name}</span></button>;
      })}</nav>
      <div className="sidebar-footer"><div className="side-source"><span className="source-symbol"><Globe2 size={18}/></span><span><b>NASA POWER</b><small>Fuente de clima histórico</small></span></div>
        <div className="sidebar-bottom"><span className="status-dot"/> Aplicación web <Leaf size={13}/></div>
      </div>
    </aside>
    <div className="surface">
      <header className="topbar">
        <div className="breadcrumb"><button data-tour="mobile-navigation" className="icon-btn mobile-menu" aria-label="Abrir menú" onClick={()=>setMenu(!menu)}>{menu?<X size={20}/>:<Menu size={20}/>}</button>
          <span className="crumb-home">Espacio de trabajo</span><span className="slash">/</span><strong>{title}</strong></div>
        <div className="profile-wrap"><button data-tour="profile" className="profile" aria-expanded={profile} onClick={()=>setProfile(!profile)}><span className="avatar">{user.name[0].toUpperCase()}</span><b>{firstName}</b><ChevronDown size={14}/></button>
          {profile&&<div className="profile-menu card"><b>{user.name}</b><small>{user.email}</small><button className="button secondary" onClick={()=>{route('/');setShowGuide(true);}}>Ver guía</button><button className="button secondary" onClick={close}><LogOut size={16}/> Cerrar sesión</button></div>}</div>
      </header>
      <main className="main">
        {error&&<div className="error" role="alert">{error} <button className="text-button" onClick={refresh}>Reintentar</button></div>}
        {section===''&&<Dashboard user={user} sites={sites} runs={runs} reports={reports} go={route}/>}
        {section==='lotes'&&!parts[1]&&<><div className="page-heading" data-tour="lots"><div><h1>Mis lotes</h1><p>Dibuja tu terreno o guarda un punto de consulta exploratorio.</p></div><button className="button primary" onClick={()=>route('/lotes/nuevo')}><Plus size={18}/> Nuevo lote</button></div>
          <section className="card panel">{sites.length?sites.map(s=><SiteRow site={s} go={route} key={s.id}/>):<p className="muted">Todavía no hay lotes guardados.</p>}</section></>}
        {section==='lotes'&&parts[1]&&<FieldEditor key={parts[1]} id={parts[1]==='nuevo'?null:parts[1]} analyzing={parts[2]==='analizar'} go={route} refresh={refresh}/>}
        {section==='comparar'&&parts[1]&&<Compare key={parts[1]} id={parts[1]} summary={runs.find(r=>r.id===parts[1])} go={route} refresh={refresh}/>}
        {section==='comparar'&&!parts[1]&&<><div className="page-heading" data-tour="runs"><div><h1>Comparar rotaciones</h1><p>Consulta los escenarios y recupera análisis guardados.</p></div><button className="button primary" onClick={()=>route('/lotes')}><MapPin size={17}/> Elegir lote</button></div>
          <section className="card panel">{runs.length?runs.map(run=><button key={run.id} className="site-row" onClick={()=>route('/comparar/'+run.id)}><span className="site-icon"><Activity size={19}/></span><span className="site-name"><b>{run.field_name}</b><small>{day(run.created)}</small></span><StatusChip status={run.status}/><ArrowRight size={17}/></button>):<Empty icon="analysis" title="Tu primera comparación" text="Abre un lote y selecciona Analizar para comparar rotaciones."/>}</section></>}
        {section==='informes'&&<><div className="page-heading" data-tour="reports"><div><h1>Informes</h1><p>Descarga los documentos y la evidencia de los análisis.</p></div><button className="button secondary" onClick={()=>route('/comparar')}><ArrowLeft size={16}/> Comparaciones</button></div>
          <section className="card panel">{reports.length?reports.map(r=><article key={r.id} className="report-row"><div className="site-name"><b>{r.field_name}</b><small>{day(r.created)} · Folio {r.id.slice(0,8)}</small></div><StatusChip status={r.status}/>{r.ready?<div className="button-row">
            <a className="button primary small" href={'/api/reports/'+r.id+'/pdf'}><ArrowDownToLine size={16}/> PDF</a><a className="button secondary small" href={'/api/reports/'+r.id+'/csv'}>CSV</a>
            <a className="button secondary small" href={'/api/reports/'+r.id+'/daily'}>Serie diaria</a></div>:['failed','cancelled'].includes(r.status)&&<button className="button secondary small" onClick={()=>void post('/jobs/'+r.job_id+'/retry').then(refresh).catch(e=>setError(errorText(e)))}>Reintentar</button>}</article>):<Empty icon="report" title="Aún no hay informes" text="Abre una comparación y selecciona la rotación que quieres exportar."/>}</section></>}
      </main>
    </div>
    {showGuide&&sites.length>0&&<GuidedTour pilot={(sites.find(s=>s.pilot)??sites[0]).id}
      run={runs.find(r=>r.status==='done')?.id} navigate={route} onFinish={()=>{setShowGuide(false);route('/');}}/>}
  </div>;
}

export function Empty({icon,title,text}:{icon:'analysis'|'report';title:string;text:string}) {
  return <div className="empty"><span className="metric-icon">{icon==='analysis'?<Activity size={22}/>:<FileText size={22}/>}</span><h2>{title}</h2><p>{text}</p></div>;
}

export function StatusChip({status}:{status:RunSummary['status']}) {
  return <span className={'chip '+(status==='failed'?'chip-error':'')}>{{queued:'En cola',running:'En proceso',done:'Listo',failed:'Requiere atención',cancelled:'Cancelado'}[status]}</span>;
}
