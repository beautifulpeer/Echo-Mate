// Single-page connection, acquisition and read-only signal replay.
let previewing = false, waveformCursor = 0, waveformSession = null;
let frozenPoints = null;
let autoPreviewSession = null;
const savedShowPage = showPage;
showPage = next => {
  const configure=next==='settings'||next==='connection-page';
  if(configure)next='devices-page';
  stopMove();page=next;
  document.querySelectorAll('.page').forEach(element=>element.hidden=element.id!==next);
  document.querySelectorAll('[data-page]').forEach(button=>button.classList.toggle('active',button.dataset.page===next));
  $('breadcrumb').textContent={'connection-page':'设备连接',home:'设备总览',history:'历史记录','devices-page':'设备管理'}[next];
  if(next==='history')loadRecords();
  else {playing=false;replay=null;$('replay').hidden=true;}
  if(next==='devices-page')refreshDevices();
  updateDisabled();requestAnimationFrame(()=>{draw();window.dispatchEvent(new Event('resize'));});
  if(configure)$('device-configuration').scrollIntoView({behavior:'smooth',block:'start'});
};
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>showPage(button.dataset.page));
$('configure').onclick = () => showPage('settings');
$('connection-settings').onclick = () => showPage('settings');
$('add-device').onclick=()=>showPage('settings');
const deviceLabel=document.createElement('label');deviceLabel.className='device-label';deviceLabel.textContent='设备名称（选填）';
const deviceLabelInput=document.createElement('input');deviceLabelInput.id='device-label';deviceLabelInput.maxLength=100;deviceLabelInput.placeholder='例如：客厅温湿度';
deviceLabelInput.oninput=()=>{linkConfig.name=deviceLabelInput.value;};deviceLabel.append(deviceLabelInput);
$('device-configuration').querySelector('.configuration-body>.connection-fields').prepend(deviceLabel);

function refreshMethods() {
  if($('device-label'))$('device-label').value=linkConfig.name||'';
  const container = $('connection-methods'); container.replaceChildren();
  for (const option of $('connection-kind').options) {
    const button = document.createElement('button');button.type='button';
    button.textContent = connectionNames[option.value];
    button.className = linkConfig.kind === option.value ? 'active' : '';
    button.setAttribute('aria-pressed', String(linkConfig.kind === option.value));
    button.disabled = !!window.connectionBusy;
    button.onclick = () => {
      if(window.connectionBusy)return;
      linkConfig = {kind:option.value,...linkDefaults[option.value]};
      linkPassword='';persistLink();renderLinkFields();
    };
    container.append(button);
  }
}
const originalRenderLinkFields = renderLinkFields;
renderLinkFields = () => { originalRenderLinkFields();refreshMethods(); };
refreshMethods();

async function captureStart() {
  if (!state?.connected || state.recording || window.captureBusy) return;
  window.captureBusy=true;
  try {
    replayRequest++;replay=null;playing=false;$('replay').hidden=true;
    paused=false;frozenPoints=null;points=[];previewing=false;
    await command('record', true);
  } finally { window.captureBusy=false; }
}
async function captureStop() {
  if(window.captureBusy)return;
  window.captureBusy=true;
  try { if(state?.recording)await command('record',false);previewing=false;await loadRecords(); }
  finally {window.captureBusy=false;}
}
$('preview-start').onclick=()=>{
  if(!state?.connected || state.recording)return;
  replayRequest++;replay=null;playing=false;$('replay').hidden=true;
  previewing=!previewing;paused=false;frozenPoints=null;points=[];
  toast(previewing?'波形预览，不保存数据':'预览已停止');
};
$('capture-start').onclick=captureStart;$('capture-stop').onclick=captureStop;
$('pause').onclick=()=>{paused=!paused;frozenPoints=paused?points.slice():null;$('pause').textContent=paused?'继续画面':'暂停画面';draw();};
$('wave-fullscreen').onclick=async()=>{
  const panel=document.querySelector('[data-module="waveform"]');
  try {
    if(document.fullscreenElement)await document.exitFullscreen();
    else if(panel.requestFullscreen)await panel.requestFullscreen();
    else {panel.classList.toggle('expanded-waveform');draw();}
  }catch{panel.classList.toggle('expanded-waveform');draw();}
};
document.addEventListener('fullscreenchange',()=>{$('wave-fullscreen').textContent=document.fullscreenElement?'退出全屏':'全屏';draw();});
function deviceSignal(connection) {
  const values=connection?.values||{};
  const wifi=Number.isFinite(values.wifi_rssi)||Object.hasOwn(values,'wifi_signal_age_ms');
  const strength=wifi?values.wifi_rssi:values.rssi;
  const age=values.wifi_signal_age_ms;
  const expired=!!connection?.stale||(wifi&&Number.isFinite(age)&&(age<0||age>15000));
  const valid=!!connection?.connected&&!expired&&Number.isFinite(strength)&&strength>=-127&&strength<=0;
  const bars=valid?(strength>=-55?4:strength>=-67?3:strength>=-80?2:1):0;
  const quality=['未上报','较弱','一般','良好','很好'][bars];
  const medium=wifi?'设备 Wi-Fi':connection?.kind==='ble'?'蓝牙':'无线信号';
  return {bars,label:`${medium}：${valid?`${quality}（${strength} dBm，${bars}/4 格）`:expired?'数据已过期':'未上报'}`};
}
function signalIndicator(connection) {
  const info=deviceSignal(connection),button=document.createElement('button');
  button.className='signal-strength';button.type='button';button.title=info.label;
  button.setAttribute('aria-label',info.label);button.onclick=()=>toast(info.label);
  for(let i=0;i<4;i++){const bar=document.createElement('i');bar.classList.toggle('on',i<info.bars);button.append(bar);}
  return button;
}
const workbenchUpdate = update;
update = next => {
  const session = `${next.device_id||''}:${next.connection?.kind}:${next.connection?.session_id||''}`;
  if(session!==waveformSession){waveformSession=session;waveformCursor=0;points=[];frozenPoints=null;controlDrafts.clear();colorDraftDirty=false;colorSubmitted=null;}
  if(!next.connected)previewing=false;
  const properties=next.capabilities||next.connection?.values?.capabilities;
  if(next.connected&&properties?.signals?.length&&autoPreviewSession!==session){autoPreviewSession=session;if(!next.recording)previewing=true;}
  if(!next.connected)autoPreviewSession=null;
  workbenchUpdate(next);
  const rate=next.connection?.packet_rate;$('packet-rate').textContent=' · 得包率 '+(Number.isFinite(rate)?rate.toFixed(1)+'%':'—');$('packet-rate').title='按设备采样序号统计；无序号时不估算';
  const signal=deviceSignal(next.connection);
  $('wireless-status').textContent=`${connectionNames[next.connection?.kind]||'连接'} · ${signal.label} · ${next.connected?(next.connection?.stale?'链路已连，数据已过期':'已连接'):'已断开'}`;
  $('wireless-status').append(signalIndicator(next.connection));
  $('capture-start').disabled=!next.connected||next.recording||window.captureBusy;
  $('capture-stop').disabled=(!next.recording&&!previewing)||window.captureBusy;
  $('preview-start').disabled=!next.connected||next.recording||window.captureBusy;
  $('preview-start').textContent=previewing?'停止预览':'波形预览';
  $('record-status').textContent=next.recording?'● 正在采集':previewing?'● 预览 · 不保存':'待采集';
  $('live').textContent=!next.connected?'未连接':paused?'画面已暂停':next.recording?'正在采集':previewing?'预览 · 不保存':'待采集';
  $('settings-disconnect').disabled=window.connectionBusy||!next.connected;
  for(const id of ['archive-load','archive-export','archive-delete'])$(id).disabled=!chosenRecord()||!!next.recording;
};
async function refreshWaveform(){
  const session=waveformSession;
  try {
    const response=await fetch('/api/waveform?after='+waveformCursor,{signal:AbortSignal.timeout(3000)});
    if(!response.ok)throw Error();const result=await response.json();
    if(session!==waveformSession)return;
    waveformCursor=result.cursor;
    if((previewing||state?.recording)&&state?.connected&&result.samples.length){
      points.push(...result.samples);const end=points.at(-1).time;
      points=points.filter(p=>p.time>=end-20).slice(-5000);
      if(result.gap)log('显示缓存已跳过旧帧；采集保存不受显示缓存影响');
      draw();
    }
  }catch{}finally{setTimeout(refreshWaveform,100);}
}
function chosenRecord(){return history.find(record=>record.id===$('record-select').value);}
$('archive-load').onclick=()=>{const record=chosenRecord();if(record)openReplay(record);};
$('record-select').onchange=()=>{
  const record=chosenRecord();$('archive-info').textContent=record?`${record.count} 帧 · ${duration(record.seconds||0)} · ${connectionNames[record.source]||record.source||''}`:'尚未选择记录';
  for(const id of ['archive-load','archive-export','archive-delete'])$(id).disabled=!record||!!state?.recording;
};
$('archive-export').onclick=()=>{const record=chosenRecord();if(!record||state?.recording)return;const a=document.createElement('a');a.href='/api/records/export?format=csv&id='+encodeURIComponent(record.id);a.download=`LitePanel-${record.id}.csv`;a.click();};
$('archive-delete').onclick=()=>{const record=chosenRecord();if(record)requestDelete(record);};
loadRecords=async()=>{
  try{
    const response=await fetch('/api/records?summary=1');if(!response.ok)throw Error();history=await response.json();
    const select=$('record-select'),previous=select.value;select.replaceChildren();
    const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=history.length?'请选择采集记录':'尚无采集记录';select.append(placeholder);
    for(const record of history){const option=document.createElement('option');option.value=record.id;option.textContent=`${record.name} · ${record.count} 帧 · ${duration(record.seconds||0)}`;select.append(option);}
    select.value=history.some(r=>r.id===previous)?previous:history[0]?.id||'';
    select.onchange();
  }catch{toast('记录加载失败，请检查后台服务');}
};
$('refresh-records').onclick=loadRecords;
loadRecords();refreshWaveform();

const packetRateBadge=document.createElement('small');packetRateBadge.id='packet-rate';document.querySelector('.waveform-title').append(packetRateBadge);
let devicesBusy=false;
function renameDevice(device){
  const dialog=document.createElement('dialog'),form=document.createElement('form');form.className='device-rename-form';
  const title=document.createElement('h2');title.textContent='修改设备名称';
  const label=document.createElement('label');label.textContent='设备名称';
  const input=document.createElement('input');input.value=device.name;input.maxLength=100;input.required=true;label.append(input);
  const note=document.createElement('p');note.textContent='保存为上位机别名，无需断开连接，不修改设备属性。';
  const error=document.createElement('p');error.setAttribute('role','alert');
  const actions=document.createElement('div');actions.className='dialog-actions';
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='取消';cancel.onclick=()=>dialog.close();
  const save=document.createElement('button');save.type='submit';save.textContent='保存名称';save.className='primary';actions.append(cancel,save);
  form.append(title,label,note,error,actions);dialog.append(form);document.body.append(dialog);dialog.onclose=()=>dialog.remove();
  form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{await linkRequest('/api/devices/rename',{id:device.id,name:input.value});dialog.close();await refreshDevices();toast('设备名称已保存');}catch(e){error.textContent=e.message;save.disabled=false;}};
  dialog.showModal();input.focus();input.select();
}
async function deviceOperation(action,id){
  if(devicesBusy)return;
  devicesBusy=true;
  try{
    await refreshDevices();
    const response=await fetch('/api/state');
    if(!response.ok)throw Error('无法确认当前采集状态，请稍后重试');
    const current=await response.json();update(current);
    if(current.recording){
      const operation={select:'切换设备',remove:'断开并移除设备',reconnect:'重新连接设备'}[action]||'操作设备';
      if(!window.confirm('当前设备正在采集。是否先停止并保存已采集的数据，再'+operation+'？'))return;
      if(!await command('record',false))return;
    }
    stopMove();await linkRequest('/api/devices/'+action,{id});
    previewing=false;points=[];frozenPoints=null;waveformCursor=0;
    paused=false;playing=false;replay=null;$('replay').hidden=true;
    controlDrafts.pending.clear();
    update(await (await fetch('/api/state')).json());
    await refreshDevices();if(action==='select')showPage('home');
  }catch(error){toast(error.message);}finally{devicesBusy=false;await refreshDevices();}
}
async function refreshDevices(){
  try{
    const response=await fetch('/api/devices');if(!response.ok)throw Error('设备列表加载失败');
    const result=await response.json();const devices=result.devices||[];
    const list=$('device-list'),select=$('overview-device');list.replaceChildren();select.replaceChildren();
    const empty=document.createElement('option');empty.value='';empty.textContent='请选择设备';select.append(empty);
    for(const device of devices){
      const c=device.connection,row=document.createElement('div');row.className='managed-device';row.setAttribute('role','listitem');
      const info=document.createElement('div'),name=document.createElement('strong'),detail=document.createElement('p');
      name.textContent=device.name+(device.active?' · 当前设备':'');
      const rssi=c.values?.wifi_rssi??c.values?.rssi;
      detail.textContent=`${connectionNames[c.kind]||c.kind} · ${c.connected?'已连接':'已断开'}${c.stale?' · 等待上报':''}`;
      if(['ble','wifi','mqtt'].includes(c.kind)){
        const signal=signalIndicator(c);detail.append(signal);
      }
      if(!c.connected&&c.error){const reason=document.createElement('small');reason.textContent=c.error;detail.append(reason);}
      info.append(name,detail);row.append(info);
      const choose=document.createElement('button');choose.textContent=device.active?'当前查看':'查看与控制';choose.disabled=device.active||devicesBusy;choose.onclick=()=>deviceOperation('select',device.id);
      const remove=document.createElement('button');remove.textContent='断开并移除';remove.disabled=devicesBusy;remove.onclick=()=>deviceOperation('remove',device.id);
      const rename=document.createElement('button');rename.textContent='重命名';rename.onclick=()=>renameDevice(device);
      if(!device.active)row.append(choose);
      if(!c.connected){const reconnect=document.createElement('button');reconnect.textContent='\u91cd\u65b0\u8fde\u63a5';reconnect.disabled=devicesBusy;reconnect.onclick=()=>deviceOperation('reconnect',device.id);row.append(reconnect);}
      row.append(rename,remove);list.append(row);
      const option=document.createElement('option');option.value=device.id;option.textContent=device.name+(c.connected?' · 在线':' · 离线');select.append(option);
    }
    select.value=result.active_id||'';select.disabled=devicesBusy;
    $('devices-error').textContent=devices.length?'连接会话由当前后台服务持有，后台重启后需重新连接。':'尚未添加设备，请到设备连接中扫描或填写参数。';
  }catch(error){$('devices-error').textContent=error.message;}
}
$('overview-device').onchange=event=>{if(event.target.value)deviceOperation('select',event.target.value);};
setInterval(refreshDevices,3000);refreshDevices();
