import { lazy, Suspense, useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, CloudSun, FileUp, FlaskConical, Info, MapPin, Save, Sprout } from 'lucide-react';
import { api,day,errorText,n,post } from './client';
import type { Crop, ImportRecord, Job, Shape, Site, Task } from './types';
import type { Go } from './App';
import { SoilDetails, SoilPanel, useSoil } from './SoilProfile';

const Map=lazy(()=>import('./Map'));
const kindLabels={climate:'Clima',soil:'Suelo',campaigns:'Campañas'};

export function FieldEditor({id,analyzing,go,refresh}:{id:string|null;analyzing:boolean;go:Go;refresh:()=>Promise<void>}) {
  const [site,setSite]=useState<Site|null>(),[name,setName]=useState(''),[shape,setShape]=useState<Shape|null>(null);
  const [source,setSource]=useState('dibujo manual'),[error,setError]=useState(''),[saved,setSaved]=useState('');
  const [busy,setBusy]=useState(false),[dirty,setDirty]=useState(false);
  const [records,setRecords]=useState<ImportRecord[]>([]);
  const [loadError,setLoadError]=useState('');

  function load(){
    setLoadError('');
    if(!id){setSite(null);return;}
    void api<Site>('/fields/'+id).then(x=>{setSite(x);setName(x.name);setShape(x.geometry);setSource(x.source);}).catch(e=>setLoadError(errorText(e)));
  }
  function loadImports(){if(id)void api<ImportRecord[]>('/fields/'+id+'/imports').then(setRecords).catch(e=>setError(errorText(e)));}
  useEffect(()=>{load();loadImports();},[id]);

  async function save(e:FormEvent) {
    e.preventDefault();
    if(!shape){setError('Marca un punto o termina de dibujar el terreno.');return;}
    setBusy(true);setError('');setSaved('');
    try {
      const data={name,geometry:shape,source,version:site?.version};
      const item=id?await api<Site>('/fields/'+id,{method:'PATCH',body:JSON.stringify(data)}):await post<Site>('/fields',data);
      setSite(item);setName(item.name);setDirty(false);setSaved('Lote guardado.');void refresh();
      if(!id)go('/lotes/'+item.id);
    }catch(e){setError(errorText(e));}finally{setBusy(false);}
  }

  if(loadError)return <div className="card panel"><p role="alert">{loadError}</p><button className="button secondary" onClick={load}>Reintentar</button></div>;
  if(site===undefined)return <p className="muted loading">Cargando lote…</p>;
  if(analyzing&&site)return <AnalysisForm site={site} go={go}/>;
  return <>
    <button className="back-link" onClick={()=>go('/lotes')}><ArrowLeft size={16}/> Mis lotes</button>
    <div className="page-heading"><div><h1>{site?.name??'Nuevo lote'}</h1><p>{site?.pilot?'Punto piloto · Santa Cruz, Bolivia':'Ubicación y datos del terreno'}</p></div>
      {site&&<button className="button primary" disabled={dirty||site.multicell} onClick={()=>go('/lotes/'+site.id+'/analizar')}><Sprout size={18}/> Analizar <ArrowRight size={16}/></button>}</div>
    <form onSubmit={save}>
      <div className="editor-grid">
        <section className="card panel map-panel"><div className="section-head"><div><h2>Ubicación del lote</h2><p>Marca un punto o dibuja un perímetro para calcular el área.</p></div></div>
          <Suspense fallback={<div className="map-stage loading">Cargando editor de mapa…</div>}><Map initial={shape} onShape={(geo,s)=>{setShape(geo);setSource(s);setDirty(true);setSaved('');}}/></Suspense>
        </section>
        <section className="card panel field-info" data-tour="field-info"><MapPin className="green" size={23}/><h2>Ficha del terreno</h2>
          <label>Nombre del lote<input value={name} onChange={e=>{setName(e.target.value);setDirty(true);}} minLength={2} maxLength={100} required placeholder="Ej. Lote norte"/></label>
          <dl className="facts"><div><dt>Geometría</dt><dd>{shape?.type==='Point'?'Punto':shape?'Perímetro':'Por definir'}</dd></div>
          <div><dt>Superficie</dt><dd>{site?.area_ha&&!dirty?n(site.area_ha,2)+' ha':shape&&shape.type!=='Point'?'Al guardar':'—'}</dd></div>
          <div><dt>Coordenadas</dt><dd>{shape?.type==='Point'?shape.coordinates.slice().reverse().map(x=>x.toFixed(6)+'°').join(', '):site&&!dirty?site.lat.toFixed(6)+'°, '+site.lon.toFixed(6)+'°':'—'}</dd></div>
          <div><dt>Versión guardada</dt><dd>{site?.version??'—'}</dd></div></dl>
          {site?.multicell ? <p className="notice"><Info size={17}/> El perímetro se marcó para evaluación multicelda. Usa un punto exploratorio o divide el terreno.</p> :
            site?.pilot&&<p className="notice"><CloudSun size={17}/> El CSV verificado cubre el punto piloto. Si cambias su ubicación se consultará su propia serie.</p>}
          {dirty&&site&&<p className="muted">Guarda los cambios para habilitar el análisis.</p>}
          {error&&<p className="error" role="alert">{error}</p>}{saved&&<p className="success" role="status">{saved}</p>}
          <button className="button primary" disabled={busy||(!dirty&&!!site)}><Save size={16}/> {busy?'Guardando…':'Guardar'}</button>
        </section>
      </div>
    </form>
    {site&&<><SoilPanel key={site.version} site={site} disabled={dirty}/><Imports site={site} records={records} refresh={loadImports}/></>}
  </>;
}

function Imports({site,records,refresh}:{site:Site;records:ImportRecord[];refresh:()=>void}) {
  const [open,setOpen]=useState(false),[kind,setKind]=useState<keyof typeof kindLabels>('climate');
  const [file,setFile]=useState<File|null>(null),[headers,setHeaders]=useState(''),[error,setError]=useState('');
  const [job,setJob]=useState<Job>(),[busy,setBusy]=useState(false),[taskId,setTaskId]=useState('');
  useEffect(()=>{
    if(!taskId)return;
    let active=true;
    let timer:number|undefined;
    const poll=async()=>{
      try{const j=await api<Job>('/jobs/'+taskId);if(!active)return;setJob(j);
        if(j.status==='queued'||j.status==='running')timer=window.setTimeout(poll,1300);else refresh();}
      catch(e){if(active)setError(errorText(e));}
    };
    void poll();return()=>{active=false;clearTimeout(timer);};
  },[taskId]);
  async function select(next:File|null) {
    setError('');setHeaders('');setFile(null);
    if(!next)return;
    if(next.size>20*1024*1024){setError('El CSV supera 20 MiB.');return;}
    try {
      const text=await next.slice(0,24000).text();
      const lines=text.replace(/^\uFEFF/,'').split(/\r?\n/);
      const idx=lines[0]?.trim()==='-BEGIN HEADER-'?lines.findIndex(l=>l.trim()==='-END HEADER-')+1:0;
      if(!lines[idx])throw new Error('No pudimos detectar encabezados.');
      setHeaders(lines[idx]);setFile(next);
    }catch(e){setError(errorText(e));}
  }
  async function upload(e:FormEvent) {
    e.preventDefault();if(!file)return;
    setBusy(true);setError('');setJob(undefined);setTaskId('');
    const body=new FormData();body.append('kind',kind);body.append('file',file);
    try{const res=await api<Task>('/fields/'+site.id+'/imports',{method:'POST',body});setTaskId(res.job_id);}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  return <section className="card panel" data-tour="imports"><div className="section-head"><div><h2>Datos del lote</h2><p>Importa las observaciones que usarás para revisar el análisis.</p></div>
    <button className="button secondary" onClick={()=>setOpen(!open)} aria-expanded={open}><FileUp size={17}/> Importar CSV</button></div>
    {open&&<form className="import-form" onSubmit={upload}><div className="two-col"><label>Tipo de datos<select value={kind} onChange={e=>{setKind(e.target.value as keyof typeof kindLabels);setError('');}}>
      {Object.entries(kindLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <label>Archivo CSV<input type="file" accept=".csv,text/csv" onChange={e=>void select(e.target.files?.[0]??null)}/></label></div>
      <p className="muted">UTF-8, coma, decimal con punto y fechas AAAA-MM-DD. {kind!=='climate'&&<>Usa este identificador en field_id: <code>{site.id}</code></>}</p>
      {headers&&<p className="notice headers"><strong>Encabezados detectados</strong> {headers}</p>}
      {error&&<p className="error" role="alert">{error}</p>}
      {job&&<p className={job.status==='failed'?'error':'notice'} aria-live="polite">{job.status==='done'?'Importación completada.':job.error??('Proceso '+job.progress+' %')}</p>}
      <div className="button-row"><a className="button secondary" href={'/api/templates/'+kind}>Descargar plantilla</a>
        <button className="button primary" disabled={!file||busy||job?.status==='running'||job?.status==='queued'}>Cargar archivo</button></div>
    </form>}
    {records.map(r=><div key={r.id} className="import-row"><b>{kindLabels[r.kind as keyof typeof kindLabels]}</b> · {day(r.created)} · {r.summary?n(r.summary.rows)+' filas'+(r.summary.missing_days?' · '+r.summary.missing_days+' días ausentes':''):r.error??r.status}</div>)}
  </section>;
}

function AnalysisForm({site,go}:{site:Site;go:Go}) {
  const [irrigation,setIrrigation]=useState('unknown'),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [trial,setTrial]=useState(false);
  const [differentMonths,setDifferentMonths]=useState(false),[months,setMonths]=useState([11,11,11]);
  const [crops,setCrops]=useState<Crop[]>([]),[allowed,setAllowed]=useState<string[]>([]),[regional,setRegional]=useState(false);
  const soil=useSoil(site);
  const canUseSoil=!!soil.profile?.retention.length&&soil.profile.retention[0].fc!==null&&soil.profile.retention[0].wp!==null;
  useEffect(()=>{let active=true;void api<Crop[]>('/crops').then(data=>{if(active){setCrops(data);setAllowed(data.filter(c=>c.simulated).map(c=>c.code));}})
    .catch(e=>{if(active)setError(errorText(e));});return ()=>{active=false;};},[]);
  async function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();setBusy(true);setError('');
    const form=new FormData(e.currentTarget);
    const body:Record<string,unknown>={previous:form.get('previous'),priority:form.get('priority'),irrigation,trial,
      allowed_crops:allowed,use_regional_soil:regional};
    if(differentMonths)body.plant_months=months;
    for(const k of ['irrigation_mm','theta_fc','theta_wp','depth_m','soil_ph','soil_ec','plant_month','elevation_m','rainfall_shift_pct','warming_c']){
      const value=form.get(k);if(value!=null&&value!=='')body[k]=Number(value);
    }
    try{const task=await post<Task>('/fields/'+site.id+'/analyses',body);go('/comparar/'+task.target_id);}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  return <>
    <button className="back-link" onClick={()=>go('/lotes/'+site.id)}><ArrowLeft size={16}/> {site.name}</button>
    <div className="page-heading"><div><h1>Preparar análisis</h1><p>{site.name} · versión {site.version} del lote</p></div></div>
    <form className="analysis-layout" onSubmit={submit}>
      <section className="card panel"><div className="section-head"><div><h2>Manejo y objetivos</h2><p>Usa los datos que puedes confirmar del terreno.</p></div></div>
        <div className="two-col form-gap" data-tour="management"><label>Cultivo anterior<select name="previous" defaultValue="unknown"><option value="unknown">No lo sé</option>{crops.map(c=><option key={c.code} value={c.code}>{c.name}</option>)}</select></label>
        <label>Disponibilidad de riego<select value={irrigation} onChange={e=>setIrrigation(e.target.value)}><option value="unknown">No lo sé</option><option value="rainfed">Solo lluvia</option><option value="confirmed">Riego confirmado</option></select></label>
        {irrigation==='confirmed'&&<label>Riego máximo (mm/día)<input type="number" name="irrigation_mm" min=".1" max="100" step=".1" required/></label>}
        <label data-tour="priority">Prioridad<select name="priority" defaultValue="balanced"><option value="balanced">Equilibrada</option><option value="water">Menor déficit de agua</option><option value="cover">Mayor cobertura y protección del suelo</option><option value="diversity">Diversidad de familias</option></select></label>
        <label>Mes de siembra<select name="plant_month" value={months[0]} onChange={e=>setMonths([Number(e.target.value),Number(e.target.value),Number(e.target.value)])}>{monthNames.map((m,i)=><option value={i+1} key={m}>{m}</option>)}</select></label></div>
        <div className="form-details" data-tour="calendar"><label className="check-label"><input type="checkbox" checked={differentMonths} onChange={e=>setDifferentMonths(e.target.checked)}/><span>Elegir un mes por campaña anual</span></label>
          {differentMonths&&<div className="campaign-months">{months.map((month,i)=><label key={i}>Campaña {i+1}<select aria-label={'Mes de campaña '+(i+1)} value={month} onChange={e=>setMonths(months.map((v,j)=>j===i?Number(e.target.value):v))}>{monthNames.map((m,j)=><option value={j+1} key={m}>{m}</option>)}</select></label>)}</div>}
          <p className="muted">Tres campañas en años sucesivos. Cada ventana local y duración necesita confirmación. El análisis descarta secuencias que se solapen.</p></div>
        <details className="form-details"><summary data-tour="crops">Cultivos disponibles ({allowed.length} de {crops.filter(c=>c.simulated).length})</summary>
          <p className="muted">Desmarca los cultivos que no tienes previsto manejar por semilla, equipo, comprador o uso. Elige al menos tres. Las ventanas son orientativas para Santa Cruz.</p>
          <div className="crop-selection">{crops.filter(c=>c.simulated).map(c=><label className="check-label" key={c.code}><input type="checkbox" checked={allowed.includes(c.code)}
            onChange={e=>setAllowed(e.target.checked?[...allowed,c.code]:allowed.filter(x=>x!==c.code))}/><span>{c.name}</span></label>)}</div></details>
        <details className="form-details"><summary data-tour="analysis-soil">Perfil de suelo y elevación</summary>
          {!soil.profile&&<button type="button" className="button secondary" disabled={soil.busy} onClick={()=>void soil.consult()}>{soil.busy?'Consultando…':'Consultar SoilGrids'}</button>}
          {soil.error&&<p className="error" role="alert">{soil.error}</p>}
          {soil.profile&&<SoilDetails profile={soil.profile}/>}
          {canUseSoil&&<label className="check-label"><input type="checkbox" checked={regional} onChange={e=>setRegional(e.target.checked)}/><span>Usar retención regional estimada<small>Indica la profundidad útil observada hasta 1 m. Si tienes mediciones de retención, introdúcelas directamente.</small></span></label>}
          <div className="two-col form-gap">
          <label>Capacidad de campo (m³/m³)<input type="number" name="theta_fc" min=".001" max=".8" step=".001" placeholder="Sin dato" disabled={regional}/></label>
          <label>Punto de marchitez (m³/m³)<input type="number" name="theta_wp" min="0" max=".799" step=".001" placeholder="Sin dato" disabled={regional}/></label>
          <label>Profundidad útil (m)<input type="number" name="depth_m" min=".1" max={regional?'1':'3'} step=".01" placeholder="Sin dato" required={regional}/></label>
          <label>pH del suelo<input type="number" name="soil_ph" min="0" max="14" step=".01" placeholder="Sin dato"/></label>
          <label>Conductividad del extracto de saturación (dS/m)<input type="number" name="soil_ec" min="0" max="100" step=".01" placeholder="Sin dato"/></label>
          <label>Elevación medida (m)<input type="number" name="elevation_m" min="-450" max="8000" step="1" placeholder="Usar fuente climática si existe"/></label>
        </div></details>
        <details className="form-details"><summary data-tour="sensitivity">Sensibilidad hipotética</summary><div className="two-col form-gap">
          <label>Cambio de lluvia (%)<input type="number" name="rainfall_shift_pct" defaultValue="-15" min="-60" max="60" step=".1"/></label>
          <label>Cambio de temperatura (°C)<input type="number" name="warming_c" defaultValue="1" min="-4" max="6" step=".1"/></label></div></details>
        {crops.length>0&&<details className="form-details regional-catalog"><summary>Cultivos y producción de Santa Cruz</summary>
          <p>Referencias del Instituto Cruceño de Estadística, con datos del INE. Producción 2022–2023 preliminar, expresada en miles de toneladas. El volumen departamental ayuda a reconocer cadenas productivas.</p>
          <div className="table-scroll"><table className="data-table"><thead><tr><th>Cultivo</th><th>Producción (miles t)</th><th>Uso en la herramienta</th></tr></thead><tbody>{crops.map(c=><tr key={c.code}><td><b>{c.name}</b><small>{c.note}</small></td><td>{n(c.production_kt)}</td><td>{c.simulated?'Comparación de rotaciones':'Antecedente regional y cultivo anterior'}</td></tr>)}</tbody></table></div>
          <p><a href={crops[0].production_source} target="_blank" rel="noreferrer">Santa Cruz Estadístico 2024 · página 47</a></p>
          <p className="muted">Arroz, caña de azúcar y mandarina conservan su manejo específico en la ficha regional. Para comparar su balance se requiere adaptar anegamiento, socas o huerto perenne.</p></details>}
      </section>
      <aside className="card panel analysis-aside"><span className="metric-icon"><FlaskConical size={22}/></span><h2>Evaluación exploratoria</h2><p>El catálogo inicial es ilustrativo. Los indicadores dependen del clima histórico y de los datos declarados.</p>
        <label className="check-label"><input type="checkbox" checked={trial} onChange={e=>setTrial(e.target.checked)}/><span><b>Activar supuestos de ensayo</b><small>Completa entradas hídricas faltantes con un perfil de prueba identificado.</small></span></label>
        {error&&<p className="error" role="alert">{error}</p>}
        {crops.length>0&&allowed.length<3&&<p className="notice">Selecciona al menos tres cultivos disponibles.</p>}
        <button className="button primary" data-tour="run" disabled={busy||site.multicell||allowed.length<3}>{busy?'Enviando…':'Analizar rotaciones'}<ArrowRight size={17}/></button>
      </aside>
    </form>
  </>;
}

const monthNames='Enero Febrero Marzo Abril Mayo Junio Julio Agosto Septiembre Octubre Noviembre Diciembre'.split(' ');
