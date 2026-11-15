import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, X } from 'lucide-react';
import type { Go } from './App';

type Step={title:string;text:string;path:string;target:string};
type Box={top:number;left:number;width:number;height:number};

export function GuidedTour({pilot,run,navigate,onFinish}:{pilot:string;run?:string;navigate:Go;onFinish:()=>void}){
  const [step,setStep]=useState(0),[box,setBox]=useState<Box|null>(null),[waiting,setWaiting]=useState(true);
  const [position,setPosition]=useState({top:0,left:0});
  const dialog=useRef<HTMLDivElement>(null),next=useRef<HTMLButtonElement>(null);
  const actions=useRef({navigate,onFinish});actions.current={navigate,onFinish};
  const steps=useMemo<Step[]>(()=>{
    const lot='/lotes/'+pilot,analysis=lot+'/analizar';
    return [
      {title:'Tu espacio de planificación',text:'Desde el panel puedes abrir tu lote piloto, crear un terreno y recuperar tus análisis. Vamos a recorrer las opciones.',path:'/',target:'dashboard'},
      {title:'Muévete por la aplicación',text:'El menú reúne Panel, Mis lotes, Comparar rotaciones e Informes. En celular se abre con el botón de las tres líneas.',path:'/',target:'navigation'},
      {title:'Tus terrenos',text:'Abre un lote guardado o usa Nuevo lote. Cada cuenta conserva sus propios terrenos. El piloto permite practicar con un histórico verificado.',path:'/lotes',target:'lots'},
      {title:'Busca una ubicación',text:'Escribe una provincia, municipio o departamento. La búsqueda enfoca el mapa. Confirma el punto elegido antes de guardar.',path:lot,target:'map-search'},
      {title:'También puedes usar coordenadas',text:'En Coordenadas ingresa latitud y longitud decimales. Santa Cruz utiliza valores negativos. Pulsa Ubicar y después Confirmar punto.',path:lot,target:'coordinates'},
      {title:'Dibuja o usa el GPS',text:'Ir a mi ubicación solicita la posición del dispositivo. Dibujar terreno permite marcar vértices y cerrar el perímetro. Puedes editar y borrar la figura.',path:lot,target:'map-tools'},
      {title:'Explora las observaciones NASA',text:'Abre las capas, elige una variable y cambia la fecha o el mes. Revisa la escala y la cobertura para interpretar vegetación, humedad y lluvia.',path:lot,target:'nasa'},
      {title:'Prepara el mapa sin conexión',text:'Descarga el mapa regional mientras tengas internet. Después abre el enlace sin conexión en este mismo navegador y dispositivo para orientarte en Santa Cruz.',path:lot,target:'offline'},
      {title:'Guarda la ficha del lote',text:'El nombre, las coordenadas y la superficie quedan ligados a una versión del terreno. Guarda los cambios antes de analizar.',path:lot,target:'field-info'},
      {title:'Consulta el suelo',text:'Consultar suelo recupera predicciones regionales de textura, pH, carbono y retención de agua. Contrástalas con muestras y conocimiento local.',path:lot,target:'soil'},
      {title:'Aporta tus mediciones',text:'En Datos del lote puedes descargar plantillas e importar clima, muestras de suelo y campañas. La aplicación valida las filas y muestra el resultado de la carga.',path:lot,target:'imports'},
      {title:'Define el manejo',text:'Selecciona el cultivo anterior y la disponibilidad de riego. Declara los datos que puedas confirmar para que la comparación represente tu situación.',path:analysis,target:'management'},
      {title:'Elige tu prioridad',text:'Puedes dar mayor peso al ahorro de agua, la cobertura o la diversidad de familias. Cada alternativa explica sus resultados y sus supuestos.',path:analysis,target:'priority'},
      {title:'Ajusta el calendario',text:'Puedes mantener un mes común o elegir un mes por campaña anual para explorar transiciones de verano e invierno. Se evitan solapamientos entre cultivos.',path:analysis,target:'calendar'},
      {title:'Selecciona cultivos que puedas manejar',text:'Desmarca cultivos según semilla, equipo, uso forrajero o comprador. El catálogo muestra referencias productivas de Santa Cruz y las ventanas orientativas.',path:analysis,target:'crops'},
      {title:'Completa el perfil',text:'Introduce retención, profundidad, pH y conductividad si tienes mediciones. Puedes consultar SoilGrids y utilizar su retención estimada con una profundidad útil observada.',path:analysis,target:'analysis-soil'},
      {title:'Explora un cambio de clima',text:'Ajusta lluvia y temperatura para comparar un escenario hipotético con el mismo histórico. Estos controles ayudan a comprobar la sensibilidad de la decisión.',path:analysis,target:'sensitivity'},
      {title:'Ejecuta la comparación',text:'Analizar rotaciones inicia el trabajo. Si faltan datos puedes activar supuestos de ensayo, que aparecerán identificados en los resultados.',path:analysis,target:'run'},
      {title:'Lee los resultados',text:run?'Selecciona una alternativa, compara Histórico y Sensibilidad y revisa calendario, déficit y recomendaciones. Más abajo encontrarás tendencias, meses de estrés y procedencia.':'Aquí aparecerán tus análisis. Al terminar uno podrás elegir una alternativa, comparar escenarios y revisar recomendaciones, tendencias, meses de estrés y fuentes.',path:run?'/comparar/'+run:'/comparar',target:run?'results':'runs'},
      {title:'Descarga la evidencia',text:'Genera un informe desde la alternativa elegida. En Informes recuperas el PDF, los indicadores CSV y la serie diaria de los cálculos.',path:'/informes',target:'reports'},
      {title:'Vuelve cuando lo necesites',text:'En tu perfil puedes cerrar sesión o abrir de nuevo esta guía. El recorrido automático se muestra una vez por cuenta. Ya puedes explorar tu lote.',path:'/',target:'profile'},
    ];
  },[pilot,run]);
  const current=steps[step];

  useEffect(()=>{
    setBox(null);setWaiting(true);actions.current.navigate(current.path);
    let frame=0,settle=0,found:HTMLElement|null=null;
    const opened:HTMLDetailsElement[]=[];
    function measure(){
      if(!found)return;
      const r=found.getBoundingClientRect();
      const top=Math.max(5,r.top-6),left=Math.max(5,r.left-6);
      const width=Math.max(0,Math.min(innerWidth-10,r.width+12));
      const height=Math.max(0,Math.min(innerHeight-top-6,r.height+12));
      setBox({top,left,width,height});
      const mobile=innerWidth<621,w=Math.min(390,innerWidth-24);
      const h=dialog.current?.getBoundingClientRect().height??250;
      const below=top+height+14;
      const y=mobile?Math.max(8,innerHeight-h-12):below+h<innerHeight-12?below:Math.max(12,top-h-14);
      setPosition({top:y,left:mobile?12:Math.min(Math.max(12,left),innerWidth-w-12)});
    }
    function locate(){
      const key=current.target==='navigation'&&innerWidth<=840?'mobile-navigation':current.target;
      const element=document.querySelector<HTMLElement>(`[data-tour="${key}"]`);
      if(!element)return;
      found=element;
      let parent=element.closest('details');
      while(parent){if(!parent.open){parent.open=true;opened.push(parent);}parent=parent.parentElement?.closest('details')??null;}
      if(element.getBoundingClientRect().width===0)return;
      observer.disconnect();setWaiting(false);
      const r=element.getBoundingClientRect();
      if(r.top<80||r.bottom>innerHeight*.56){
        const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
        window.scrollBy({top:r.top-innerHeight*.22,behavior:reduced?'instant':'smooth'});
      }
      measure();
      const until=performance.now()+700;
      const animate=()=>{measure();if(performance.now()<until)frame=requestAnimationFrame(animate);};
      frame=requestAnimationFrame(animate);
      next.current?.focus({preventScroll:true});
    }
    const observer=new MutationObserver(locate);
    observer.observe(document.querySelector('main')??document.body,{childList:true,subtree:true});
    settle=window.setTimeout(()=>{observer.disconnect();setWaiting(false);},12000);
    locate();
    window.addEventListener('resize',measure);window.addEventListener('scroll',measure,true);
    const resize=new ResizeObserver(measure);if(dialog.current)resize.observe(dialog.current);
    return ()=>{observer.disconnect();resize.disconnect();cancelAnimationFrame(frame);clearTimeout(settle);
      window.removeEventListener('resize',measure);window.removeEventListener('scroll',measure,true);
      opened.forEach(d=>{d.open=false;});};
  },[current]);

  useEffect(()=>{
    function keyboard(event:KeyboardEvent){
      if(event.key==='Escape'){event.preventDefault();actions.current.onFinish();}
      if(event.key==='Tab'&&dialog.current){
        const controls=[...dialog.current.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
        const first=controls[0],last=controls.at(-1);
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    }
    document.addEventListener('keydown',keyboard);return ()=>document.removeEventListener('keydown',keyboard);
  },[]);

  return <div className="guided-tour">
    <div className="tour-blocker"/>
    {box&&<div className="tour-spotlight" style={box}/>}
    <div ref={dialog} className="tour-dialog card" role="dialog" aria-modal="true" aria-labelledby="tour-title"
      aria-describedby="tour-description" style={position}>
      <div className="tour-top"><span>Recorrido · {step+1} de {steps.length}</span>
        <button className="text-button" onClick={onFinish} aria-label="Saltar recorrido">Saltar <X size={16}/></button></div>
      <progress value={step+1} max={steps.length}/>
      <h2 id="tour-title">{current.title}</h2><p id="tour-description" aria-live="polite">{current.text}</p>
      {waiting&&<small role="status">Cargando la opción…</small>}
      {!waiting&&!box&&<small role="status">Esta vista tarda en responder. Puedes continuar o saltar el recorrido.</small>}
      <div className="tour-actions"><button className="button secondary" disabled={step===0} onClick={()=>setStep(step-1)}><ArrowLeft size={15}/> Anterior</button>
        <button ref={next} className="button primary" disabled={waiting} onClick={()=>step+1<steps.length?setStep(step+1):onFinish()}>{step+1<steps.length?'Siguiente':'Comenzar'}<ArrowRight size={15}/></button></div>
    </div>
  </div>;
}
