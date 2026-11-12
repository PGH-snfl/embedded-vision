export const ANALYSIS_MODELS=[
  {id:'gpt-6.1-sol',label:'Sol',description:'기본 전체 분석'},
  {id:'gpt-6-astra',label:'Astra',description:'전체 심화 분석'},
];
const valid=id=>ANALYSIS_MODELS.some(m=>m.id===id);
let selected=ANALYSIS_MODELS[0].id;
let disposeSelector=null;
export function selectedAnalysisModel(){return selected;}
export function analysisModelLabel(id){return ANALYSIS_MODELS.find(m=>m.id===id)?.label||'Sol';}
export function initAnalysisModel({storageKey='ev-analysis-model',storage,document:doc=document}={}){
  disposeSelector?.();disposeSelector=null;
  selected=ANALYSIS_MODELS[0].id;
  try{storage=storage||doc.defaultView.localStorage;const saved=storage.getItem(storageKey);if(valid(saved))selected=saved;}catch{}
  const menu=doc.querySelector('#agent-model-menu'),button=doc.querySelector('#agent-model-button');
  if(!menu||!button)return;
  const controller=new doc.defaultView.AbortController(),events={signal:controller.signal};
  disposeSelector=()=>controller.abort();
  const options=Array.from(menu.querySelectorAll('[data-analysis-model]'));
  function render(){
    button.textContent='분석 모델 · '+analysisModelLabel(selected)+' ▾';
    options.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.analysisModel===selected)));
  }
  options.forEach(option=>option.addEventListener('click',()=>{
    const id=option.dataset.analysisModel;if(!valid(id))return;
    selected=id;try{storage.setItem(storageKey,id);}catch{}
    render();menu.open=false;button.focus();
    doc.dispatchEvent(new doc.defaultView.CustomEvent('ev-analysis-model-change',{detail:{model:id}}));
  },events));
  menu.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();menu.open=false;button.focus();}},events);
  doc.addEventListener('click',e=>{if(!menu.contains(e.target))menu.open=false;},events);
  render();
}
