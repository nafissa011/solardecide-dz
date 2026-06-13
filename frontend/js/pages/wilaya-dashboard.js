const WilayaDashboard = {
  wilaya:null, monthly:null, radar:null, extras:null, national:null,
  wilayasList:[], charts:{},
  getName(){ return this.wilaya?.wilaya_name || this.wilaya?.nom || this.wilaya?.name || ''; },
  getState(){ return { wilayaName:this.getName() }; },
  _t(k,f=''){ return (typeof I18N!=='undefined' && I18N.t) ? (I18N.t(k)||f) : f; },
  _safe(v){ if(v===null||v===undefined) return '—'; return String(v).replace(/</g,'&lt;'); },

  async render(params={},restoreState={}){
    const content=document.getElementById('page-content');
    content.innerHTML=`<div class="page-wrapper">${Components.loading('',this._t('common.loading','Chargement…'))}</div>`;
    const id = params.name||params.wilaya||params.code||restoreState.wilayaName
            || (typeof AppState!=='undefined'?AppState.selectedWilaya?.name:'')||'Tamanrasset';
    try {
      const [stats,monthly,radar,extras,wList,nat]=await Promise.all([
        DataService.getWilayaStats(id), DataService.getWilayaMonthly(id),
        DataService.getWilayaRadar(id), DataService.getWilayaExtras(id),
        DataService.getWilayas(), DataService.getNationalStats(),
      ]);
      if(!stats) throw new Error("Wilaya inconnue : "+id);
      this.wilaya=stats; this.monthly=monthly; this.radar=radar; this.extras=extras;
      this.wilayasList=wList||[]; this.national=nat||{};
      if(typeof AppState!=='undefined') AppState.setSelectedWilaya?.({
        code:stats.wilaya_code, name:stats.wilaya_name,
        ghiAnnuel:stats.ghi_annuel_kwh_m2, potentielMW:stats.potentiel_mw,
        scoreComposite:stats.score_composite,
      });
      content.innerHTML=this.template();
      this.bindSelector(); this.renderCharts();
      if(typeof I18N!=='undefined' && I18N.applyDom) I18N.applyDom();
      this.attachActions();
    } catch(err){
      console.error('[wilaya-dashboard]',err);
      content.innerHTML=`<div class="page-wrapper"><div class="card" style="max-width:620px;margin:40px auto"><div class="card-body text-center">
        <i class="fas fa-exclamation-triangle" style="font-size:42px;color:#f59e0b"></i>
        <h3 style="margin-top:14px;color:var(--text-primary)">${this._t('dashboard.title','Dashboard wilaya')}</h3>
        <p style="color:var(--text-secondary)">${err.message||''}</p>
        <button class="btn btn-primary" onclick="App.navigate('ranking')"><i class="fas fa-arrow-left"></i> ${this._t('dashboard.back_ranking','← Classement')}</button>
      </div></div></div>`;
    }
  },

  template(){
    const w=this.wilaya||{}, ext=this.extras||{}, nat=this.national||{};
    const isFree=(window.Plan&&Plan.getPlan&&Plan.getPlan()==='free');
    const t=(k,f='')=>this._t(k,f);
    const natGhi=Number(nat.ghi_moyen_national_kwh_m2||nat.avg_ghi_annual_kwh_m2||nat.ghi_moyen||5.8);
    const natScore=Number(nat.avg_score_composite||50);
    const ghi=Number(w.ghi_annuel_kwh_m2||0), dni=Number(w.dni_moyen||0);
    const score=Number(w.score_composite||0), potMW=Number(w.potentiel_mw||0);
    const ensol=Number(w.ensoleillement_h_an||0), vent=Number(w.vent_moyen_m_s||0);
    const nbCom=Number(w.n_communes||0), rank=Number(w.rang_national||0);
    const deltaPct=(v,r)=>{ if(!r||!v)return null; return Math.round(((v-r)/r)*1000)/10; };
    const renderDelta=(d,inv=false)=>{ if(d===null||isNaN(d))return''; const ok=inv?d<0:d>0;
      const c=ok?'#10b981':'#ef4444', a=ok?'▲':'▼', s=d>0?'+':'';
      return `<span style="color:${c};font-size:12px;font-weight:600">${a} ${s}${d}% <span style="color:var(--text-muted)">${t('kpi.vs_national','vs national')}</span></span>`; };
    const ghiDelta=deltaPct(ghi,natGhi), scoreDelta=deltaPct(score,natScore);
    const pr=Number(ext.performance_ratio||0);
    const prPct=Number(ext.coverage_efficiency_pct||(pr*100)).toFixed(1);
    const tAmp=Number(ext.t2m_amplitude_c||0), demAvg=Number(ext.demand_avg_mw||0);
    const demPeak=Number(ext.demand_peak_mw||0), loadF=Number(ext.load_factor||0);
    const sunDays=Number(ext.sunny_days_year||0);

    return `<div class="page-wrapper wilaya-dashboard">
      <div class="page-header" style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between;margin-bottom:18px">
        <div>
          <h1 style="margin:0;color:var(--text-primary)"><i class="fas fa-map-marked-alt" style="color:#f59e0b"></i> ${this._safe(w.wilaya_name)}
            <span style="font-weight:400;font-size:.6em;color:var(--text-muted)">(${this._safe(w.climate_label||w.climate)})</span></h1>
          <p style="margin:6px 0 0;color:var(--text-secondary)" data-i18n="dashboard.subtitle">${t('dashboard.subtitle','Indicateurs solaires & climatiques de la wilaya')}</p>
        </div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <select id="wd-selector" class="form-control" style="min-width:220px;color:var(--text-primary);background:var(--bg-elevated)"></select>
          <button class="btn btn-outline" onclick="App.navigate('ranking')"><span data-i18n="dashboard.back_ranking">${t('dashboard.back_ranking','← Classement')}</span></button>
          <button class="btn btn-outline" onclick="App.navigate('roi',{wilaya:'${this._safe(w.wilaya_name)}'})"><span data-i18n="dashboard.go_roi">${t('dashboard.go_roi','Analyse ROI →')}</span></button>
          <button id="wd-pdf-btn" class="btn ${isFree?'btn-disabled':'btn-primary'}" ${isFree?'disabled':''}>
            <i class="fas fa-file-pdf"></i> <span>${isFree?t('dashboard.download_pdf_locked','PDF verrouillé'):t('dashboard.download_pdf','Télécharger PDF')}</span>
          </button>
        </div>
      </div>
      ${isFree?`<div style="display:flex;gap:12px;align-items:center;background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:6px;margin-bottom:18px">
        <i class="fas fa-eye" style="color:#b45309;font-size:20px"></i>
        <div style="flex:1"><strong style="color:#92400e">${t('dashboard.preview_mode','Mode aperçu')}</strong>
          <div style="font-size:13px;color:#92400e">${t('dashboard.preview_mode_desc','Passez Pro pour débloquer le PDF & la sauvegarde')}</div></div>
        <button class="btn btn-warning btn-sm" onclick="App.navigate('pricing')"><i class="fas fa-rocket"></i> <span>${t('dashboard.upgrade','Upgrader')}</span></button>
      </div>`:''}
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:24px">
        ${this._kpi('fa-sun',t('kpi.ghi_annuel','GHI annuel'),ghi.toFixed(2),t('kpi.ghi_annuel_unit','kWh/m²/an'),renderDelta(ghiDelta),'#f59e0b')}
        ${this._kpi('fa-bullseye',t('kpi.dni_moyen','DNI moyen'),dni.toFixed(3),t('kpi.dni_unit','kWh/m²/h'),'','#ef4444')}
        ${this._kpi('fa-star',t('kpi.score_composite','Score composite'),score.toFixed(1),t('kpi.score_unit','/100'),renderDelta(scoreDelta),'#10b981')}
        ${this._kpi('fa-bolt',t('kpi.potentiel_mw','Potentiel'),potMW.toFixed(1),t('kpi.potentiel_unit','MW'),'','#3b82f6')}
        ${this._kpi('fa-city',t('kpi.communes','Communes'),nbCom,'','','#6366f1')}
        ${this._kpi('fa-clock',t('kpi.ensoleillement','Ensoleillement'),ensol.toLocaleString('fr-DZ'),t('kpi.ensoleillement_unit','h/an'),'','#fbbf24')}
        ${this._kpi('fa-wind',t('kpi.vent_moyen','Vent moyen'),vent.toFixed(2),t('kpi.vent_unit','m/s'),'','#06b6d4')}
        ${this._kpi('fa-medal',t('kpi.rang_national','Rang national'),rank?'#'+rank:'—','','','#a855f7')}
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
        <div class="card"><div class="card-header"><h3 style="color:var(--text-primary);margin:0">${t('charts.monthly_dni','DNI mensuel')}</h3><small style="color:var(--text-muted)">${t('charts.monthly_dni_desc','Irradiance directe normale moyenne (W/m²)')}</small></div><div class="card-body"><canvas id="chart-dni" height="220"></canvas></div></div>
        <div class="card"><div class="card-header"><h3 style="color:var(--text-primary);margin:0">${t('charts.monthly_wind','Vent mensuel moyen')}</h3><small style="color:var(--text-muted)">${t('charts.monthly_wind_desc','Vitesse moyenne du vent à 10 m (m/s)')}</small></div><div class="card-body"><canvas id="chart-wind" height="220"></canvas></div></div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
        <div class="card"><div class="card-header"><h3 style="color:var(--text-primary);margin:0">${t('charts.performance','Profil de performance')}</h3><small style="color:var(--text-muted)">${t('charts.performance_desc','PR = GHI réel / GHI ciel clair (%)')}</small></div><div class="card-body"><canvas id="chart-pr" height="220"></canvas></div></div>
        <div class="card"><div class="card-header"><h3 style="color:var(--text-primary);margin:0">${t('charts.monthly_ghi','Irradiance mensuelle GHI')}</h3><small style="color:var(--text-muted)">${t('charts.monthly_ghi_desc','GHI mensuel (kWh/m²/mois)')}</small></div><div class="card-body"><canvas id="chart-ghi" height="220"></canvas></div></div>
      </div>
      <div class="card" style="margin-bottom:18px"><div class="card-header"><h3 style="color:var(--text-primary);margin:0">${t('charts.radar','Profil radar (5 axes)')}</h3><small style="color:var(--text-muted)">${t('charts.radar_desc','GHI · DNI · KT · Stabilité T2M · Vent (normalisé 0-100)')}</small></div><div class="card-body"><canvas id="chart-radar" height="180"></canvas></div></div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-bottom:18px">
        <div class="card"><div class="card-header"><h3 style="color:var(--text-primary);margin:0"><i class="fas fa-industry" style="color:#3b82f6"></i> ${t('infra.title','Infrastructure & rendement')}</h3></div>
          <div class="card-body">
            ${this._row('fa-percent',t('infra.performance_ratio','Performance Ratio'),`${prPct} %`,t('infra.performance_ratio_desc','PR = mean(GHI)/mean(CLRSKY_GHI)'))}
            ${this._row('fa-sun',t('infra.sunny_days','Jours très clairs'),(sunDays||'—')+' j/an',t('infra.sunny_days_desc','jours où KT moyen ≥ 0.65'))}
            ${this._row('fa-cloud',t('infra.cloudy_days','Jours nuageux'),(ext.cloudy_days_year??'—')+' j/an',t('infra.cloudy_days_desc','jours où KT moyen < 0.4'))}
            ${this._row('fa-wave-square',t('infra.instability','Instabilité GHI'),(ext.ghi_instability_pct??'—')+' %',t('infra.instability_desc','std(GHI)/mean(GHI) × 100'))}
            ${this._row('fa-plug',t('infra.demand_avg','Demande moyenne'),(demAvg?demAvg.toFixed(1):'—')+' MW',t('infra.demand_avg_desc','mean(demand_mw)'))}
            ${this._row('fa-bolt',t('infra.demand_peak','Pic de demande'),(demPeak?demPeak.toFixed(1):'—')+' MW',t('infra.demand_peak_desc','MAX(demand_mw)'))}
            ${this._row('fa-tachometer-alt',t('infra.load_factor','Facteur de charge'),(loadF?(loadF*100).toFixed(1):'—')+' %',t('infra.load_factor_desc','demand_avg / demand_peak'))}
          </div>
        </div>
        <div class="card"><div class="card-header"><h3 style="color:var(--text-primary);margin:0"><i class="fas fa-temperature-half" style="color:#ef4444"></i> ${t('climate_box.title','Climat & précipitations')}</h3></div>
          <div class="card-body">
            ${this._row('fa-thermometer-half',t('climate_box.t2m','Température moyenne'),(w.t2m_moyen??'—')+' °C')}
            ${this._row('fa-thermometer-full',t('climate_box.t2m_max','Température max'),(w.t2m_max??'—')+' °C')}
            ${this._row('fa-thermometer-empty',t('climate_box.t2m_min','Température min'),(w.t2m_min??'—')+' °C')}
            ${this._row('fa-arrows-up-down',t('climate_box.amplitude','Amplitude thermique'),(tAmp?tAmp.toFixed(1):'—')+' °C',t('climate_box.amplitude_desc','T2M_MAX − T2M_MIN'))}
            ${this._row('fa-droplet',t('climate_box.rh2m','Humidité moyenne'),(ext.rh2m_mean??w.rh2m_moyen??'—')+' %')}
            ${this._row('fa-tint',t('climate_box.precip','Précipitations annuelles'),(ext.precip_annual_mm??'—')+' mm/an')}
            ${this._row('fa-mountain',t('climate_box.climate_zone','Zone climatique'),this._safe(ext.dominant_climate||w.climate_label||w.climate))}
          </div>
        </div>
      </div>
      <div class="card" style="margin-bottom:18px"><div class="card-body">
        <p style="color:var(--text-secondary);margin:0 0 8px">${t('dashboard.info_paragraph','Toutes les valeurs sont calculées sur le dataset NASA POWER (2019-2023) via DuckDB.')}</p>
        <details><summary style="cursor:pointer;font-weight:600;color:var(--text-primary)">${t('dashboard.formulas_title','Formules utilisées')}</summary>
        <ul style="margin-top:8px;font-family:monospace;font-size:13px;line-height:1.7;color:var(--text-primary)">
          <li>GHI_annuel = mean(GHI) × 8760 / 1000</li>
          <li>Potentiel_MW = GHI_annuel × area_km² × 0.20</li>
          <li>Score_composite = 100 × (0.40·GHI + 0.20·DNI + 0.20·KT + 0.10·stab_T2M + 0.10·WS10M)</li>
          <li>Performance_Ratio = mean(GHI) / mean(CLRSKY_GHI)</li>
          <li>Amplitude_thermique = mean(T2M_MAX) − mean(T2M_MIN)</li>
          <li>Load_factor = mean(demand_mw) / MAX(demand_mw)</li>
          <li>Instabilité_GHI = std(GHI) / mean(GHI) × 100</li>
        </ul></details>
      </div></div>
    </div>`;
  },

  _kpi(icon,label,value,unit,delta='',color='#3b82f6'){
    return `<div class="kpi-card" style="background:#fff;border-left:4px solid ${color};border-radius:8px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <span style="font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted);font-weight:600">${label}</span>
        <i class="fas ${icon}" style="color:${color};opacity:.85"></i></div>
      <div style="font-size:24px;font-weight:700;margin-top:6px;color:var(--text-primary)">${value}<span style="font-size:13px;font-weight:500;color:var(--text-muted)"> ${unit||''}</span></div>
      ${delta?`<div style="margin-top:4px">${delta}</div>`:''}
    </div>`;
  },
  _row(icon,label,value,sub=''){
    return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px dashed #e2e8f0">
      <i class="fas ${icon}" style="width:18px;color:var(--text-secondary)"></i>
      <div style="flex:1"><div style="font-size:13px;color:var(--text-primary);font-weight:500">${label}</div>
      ${sub?`<div style="font-size:11px;color:var(--text-muted)">${sub}</div>`:''}</div>
      <strong style="color:var(--text-primary)">${value}</strong></div>`;
  },

  bindSelector(){
    const sel=document.getElementById('wd-selector'); if(!sel) return;
    const current=this.getName();
    const sorted=[...(this.wilayasList||[])].sort((a,b)=>(a.name||a.wilaya_name||'').localeCompare(b.name||b.wilaya_name||''));
    sel.innerHTML=sorted.map(w=>{ const n=w.name||w.wilaya_name; return `<option value="${n}" ${n===current?'selected':''}>${n}</option>`; }).join('');
    sel.onchange=e=>App.navigate('wilaya',{name:e.target.value});
  },
  attachActions(){ const b=document.getElementById('wd-pdf-btn'); if(b) b.onclick=()=>this.downloadPdf(); },
  async downloadPdf(){
    if(window.PlanGate&&PlanGate.require){ const ok=await PlanGate.require('action.wilaya_pdf','pro'); if(!ok)return; }
    else if(window.Plan&&Plan.getPlan&&Plan.getPlan()==='free'){ App.navigate('pricing'); return; }
    window.location.href=DataService.wilayaPdfUrl(this.getName());
  },

  renderCharts(){
    if(typeof Chart==='undefined') return;
    Object.values(this.charts||{}).forEach(c=>{ try{c.destroy();}catch(_){} });
    this.charts={};
    const m=this.monthly||{};
    const labels=m.labels||['Jan','Fév','Mar','Avr','Mai','Juin','Juil','Aoû','Sep','Oct','Nov','Déc'];
    const tT=(k,f='')=>this._t(k,f);

    // Graphique DNI mensuel
    const dCtx=document.getElementById('chart-dni');
    if(dCtx && Array.isArray(m.dni) && m.dni.length===12){
      this.charts.dni=new Chart(dCtx,{type:'bar',data:{labels,datasets:[{label:tT('charts.monthly_dni','DNI (W/m²)'),data:m.dni,backgroundColor:'rgba(239,68,68,0.75)',borderColor:'#ef4444',borderWidth:1}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${c.parsed.y.toFixed(2)} W/m²`}}},
          scales:{y:{beginAtZero:true,title:{display:true,text:'W/m²',color:'#9ca3af'},ticks:{color:'#9ca3af'}},x:{ticks:{color:'#9ca3af'}}}}});
    }
    // Graphique vent mensuel (avec ligne de moyenne annuelle)
    const wCtx=document.getElementById('chart-wind');
    if(wCtx && Array.isArray(m.ws10m) && m.ws10m.length===12){
      const avg=Number(m.annual_avg?.ws10m||0);
      this.charts.wind=new Chart(wCtx,{type:'line',data:{labels,datasets:[
        {label:tT('charts.monthly_wind','Vitesse vent (m/s)'),data:m.ws10m,borderColor:'#06b6d4',backgroundColor:'rgba(6,182,212,.2)',tension:.3,fill:true,pointRadius:4},
        {label:tT('charts.annual_avg','Moyenne annuelle')+' ('+avg.toFixed(2)+' m/s)',data:labels.map(()=>avg),borderColor:'#e5e7eb',borderDash:[6,4],borderWidth:2,pointRadius:0,fill:false},
      ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#e5e7eb'}}},scales:{y:{beginAtZero:true,title:{display:true,text:'m/s',color:'#9ca3af'},ticks:{color:'#9ca3af'}},x:{ticks:{color:'#9ca3af'}}}}});
    }
    // Graphique du Performance Ratio mensuel (avec ligne de moyenne annuelle)
    const pCtx=document.getElementById('chart-pr');
    if(pCtx && Array.isArray(m.pr) && m.pr.length===12){
      const prPct=m.pr.map(v=>Number((v*100).toFixed(2)));
      const avgPr=Number(((m.annual_avg?.pr??0)*100).toFixed(2));
      this.charts.pr=new Chart(pCtx,{type:'bar',data:{labels,datasets:[
        {label:tT('charts.performance','Performance Ratio (%)'),data:prPct,backgroundColor:'rgba(16,185,129,0.75)',borderColor:'#10b981',borderWidth:1},
        {label:tT('charts.annual_avg','Moyenne annuelle')+' ('+avgPr+' %)',data:labels.map(()=>avgPr),type:'line',borderColor:'#e5e7eb',borderDash:[6,4],borderWidth:2,pointRadius:0,fill:false},
      ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#e5e7eb'}},tooltip:{callbacks:{label:c=>`${c.parsed.y.toFixed(2)} %`}}},scales:{y:{beginAtZero:true,suggestedMax:100,title:{display:true,text:'%',color:'#9ca3af'},ticks:{color:'#9ca3af'}},x:{ticks:{color:'#9ca3af'}}}}});
    } else if(pCtx){
      // Données PR absentes (ancienne version du backend) : on affiche un message à la place du graphique
      const ctx=pCtx.getContext('2d'); ctx.font='14px Inter,sans-serif'; ctx.fillStyle='#64748b';
      ctx.fillText('PR indisponible (backend trop ancien)',20,40);
    }
    // Graphique GHI mensuel avec courbe de tendance
    const gCtx=document.getElementById('chart-ghi');
    if(gCtx && Array.isArray(m.ghi) && m.ghi.length===12){
      this.charts.ghi=new Chart(gCtx,{type:'bar',data:{labels,datasets:[
        {type:'bar',label:tT('charts.monthly_ghi','GHI (kWh/m²/mois)'),data:m.ghi,backgroundColor:'rgba(245,158,11,0.75)',borderColor:'#f59e0b',borderWidth:1,order:2},
        {type:'line',label:tT('charts.trend','Tendance'),data:m.ghi,borderColor:'#b45309',backgroundColor:'transparent',tension:.35,pointRadius:3,fill:false,order:1},
      ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#e5e7eb'}}},scales:{y:{beginAtZero:true,title:{display:true,text:'kWh/m²/mois',color:'#9ca3af'},ticks:{color:'#9ca3af'}},x:{ticks:{color:'#9ca3af'}}}}});
    }
    // Graphique radar des indicateurs normalisés (0-100)
    const rCtx=document.getElementById('chart-radar');
    if(rCtx && this.radar && this.radar.values){
      const axes=(this.radar.labels&&this.radar.labels.length)?this.radar.labels:[tT('radar.ghi','GHI'),tT('radar.dni','DNI'),tT('radar.kt','KT'),tT('radar.stability','Stabilité T2M'),tT('radar.wind','Vent')];
      let raw; if(Array.isArray(this.radar.values)) raw=this.radar.values.slice(0,axes.length);
      else raw=[this.radar.values.ghi??0,this.radar.values.dni??0,this.radar.values.kt??0,this.radar.values.stability??0,this.radar.values.ws10m??0];
      const data=raw.map(v=>Math.max(0,Math.min(100,Number(v)||0)));
      this.charts.radar=new Chart(rCtx,{type:'radar',data:{labels:axes,datasets:[{label:this.getName(),data,backgroundColor:'rgba(245,158,11,.25)',borderColor:'#f59e0b',borderWidth:2,pointBackgroundColor:'#f59e0b'}]},
        options:{responsive:true,maintainAspectRatio:false,scales:{r:{suggestedMin:0,suggestedMax:100,ticks:{stepSize:20,color:'#9ca3af',backdropColor:'transparent'},pointLabels:{color:'#e5e7eb',font:{weight:'600'}},grid:{color:'rgba(255,255,255,0.08)'},angleLines:{color:'rgba(255,255,255,0.12)'}}},plugins:{legend:{display:false}}}});
    }
  },
};
window.WilayaDashboard=WilayaDashboard;